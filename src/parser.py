#!/usr/bin/env python3
"""
PUML ERD (Crow's foot) -> Quarkus JPA project generator

Usage:
    python puml_to_quarkus.py input.puml output_dir base.package

What it does:
 - Parses a PlantUML ERD file containing `entity` blocks and relationship lines
   using crow's-foot tokens (e.g. `||--o{`, `}o--||`, etc.).
 - Produces a Maven Quarkus project skeleton wired for PostgreSQL + Hibernate ORM
   + REST (Resteasy Jackson) + JDBC, and generates:
     * Entities (Jakarta Persistence annotations)
     * Simple Repository classes (CDI + EntityManager)
     * JAX-RS Resource classes (CRUD endpoints using Jackson)
     * application.properties with placeholders for DB connection
     * pom.xml (Quarkus dependencies)

Limitations / heuristics:
 - Expects entity blocks like:
     entity Person {
       id : long
       name : String
     }
   or class-like declarations. Attribute lines should be `name : Type`.
 - Tries to detect `id` as primary key; otherwise first attribute becomes id.
 - Relationship parsing uses simple heuristics: token parts left/right containing
   '|' means ONE, '{' or '}' or 'o' near braces means MANY. Many side becomes owning side.
 - Does not try to guess cascade/fetch optimally; generated code uses defaults.

"""

import os
import re
import sys
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ----------------------------- Helpers ---------------------------------

def to_camel(s: str) -> str:
    return s[0].lower() + s[1:] if s else s


def to_snake(s: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()


def java_type(puml_type: str) -> str:
    t = puml_type.strip()
    mapping = {
        'int': 'Integer', 'integer': 'Integer', 'long': 'Long', 'bigint': 'Long',
        'string': 'String', 'varchar': 'String', 'text': 'String',
        'boolean': 'Boolean', 'bool': 'Boolean',
        'date': 'java.time.LocalDate', 'datetime': 'java.time.LocalDateTime',
        'float': 'Float', 'double': 'Double', 'decimal': 'java.math.BigDecimal'
    }
    return mapping.get(t.lower(), t)


def mkdirp(path: Path):
    path.mkdir(parents=True, exist_ok=True)

# ----------------------------- Parsing ---------------------------------

ENTITY_RE = re.compile(r"(?:entity|class)\s+(\w+)\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
RELATION_RE = re.compile(r"^\s*(\w+)\s*([<>\|o{}]+-{2,}>|-{2,}[<>\|o{}]+)\s*(\w+)(?:\s*:\s*(.*))?$")


def parse_entities(puml_text: str) -> Dict[str, Dict]:
    entities: Dict[str, Dict] = {}
    for m in ENTITY_RE.finditer(puml_text):
        name = m.group(1).strip()
        body = m.group(2).strip()
        attrs = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            parts = [p.strip() for p in line.split(':', 1)]
            if len(parts) == 2:
                aname, atype = parts
            else:
                aname = parts[0]
                atype = 'String'
            aname = re.sub(r'^[+\-#*]+', '', aname).strip()
            attrs.append((aname, atype))
        entities[name] = {'name': name, 'attrs': attrs}
    return entities


def detect_multiplicity(token: str) -> str:
    if '|' in token:
        return 'ONE'
    if '{' in token or '}' in token:
        return 'MANY'
    if 'o' in token and ('{' in token or '}' in token):
        return 'MANY'
    return 'UNKNOWN'


def parse_relations(puml_text: str) -> List[Dict]:
    relations = []
    for raw in puml_text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if '--' in line:
            m = RELATION_RE.match(line)
            if m:
                left, token, right, label = m.group(1), m.group(2), m.group(3), m.group(4)
            else:
                parts = line.split('--')
                if len(parts) < 2:
                    continue
                left_part = parts[0].strip()
                right_part = '--'.join(parts[1:]).strip()
                lm = re.match(r'^(\w+)\s*([\|\{\}o<>]*)$', left_part)
                rm = re.match(r'^([\|\{\}o<>]*)\s*(\w+)(?:\s*:\s*(.*))?$', right_part)
                if lm and rm:
                    left = lm.group(1)
                    token = (lm.group(2) or '') + '--' + (rm.group(1) or '')
                    right = rm.group(2)
                    label = None
                else:
                    sp = re.findall(r"(\w+)", line)
                    if len(sp) >= 2:
                        left, right = sp[0], sp[1]
                        token = '--'
                        label = None
                    else:
                        continue
            left_token = token.split('--')[0]
            right_token = token.split('--')[-1]
            relations.append({'left': left, 'left_token': left_token, 'right': right, 'right_token': right_token, 'label': (label or '').strip()})
    return relations

# ----------------------- Map relations -> JPA ---------------------------

def decide_relation_type(rel: Dict) -> Dict:
    lt = detect_multiplicity(rel['left_token'])
    rt = detect_multiplicity(rel['right_token'])
    left = rel['left']
    right = rel['right']
    label = rel.get('label') or ''

    if lt == 'ONE' and rt == 'MANY':
        return {'type': 'OneToMany', 'one': left, 'many': right, 'label': label}
    if lt == 'MANY' and rt == 'ONE':
        return {'type': 'OneToMany', 'one': right, 'many': left, 'label': label}
    if lt == 'ONE' and rt == 'ONE':
        return {'type': 'OneToOne', 'a': left, 'b': right, 'label': label}
    if lt == 'MANY' and rt == 'MANY':
        return {'type': 'ManyToMany', 'a': left, 'b': right, 'label': label}
    return {'type': 'OneToMany', 'one': left, 'many': right, 'label': label}

# ----------------------- Code generation -------------------------------

ENTITY_TEMPLATE = """package {pkg}.entities;

import jakarta.persistence.*;
import java.util.*;
{extra_imports}

@Entity
@Table(name = "{table_name}")
public class {class_name} {{

{fields}

{relations}

{getters_setters}

}}
"""

REPOSITORY_TEMPLATE = """package {pkg}.repositories;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import {pkg}.entities.{entity};
import java.util.*;

@ApplicationScoped
public class {entity}Repository {{
    @Inject
    EntityManager em;

    public {entity} find(Long id) {{
        return em.find({entity}.class, id);
    }}

    public List<{entity}> listAll() {{
        TypedQuery<{entity}> q = em.createQuery("from " + {entity}.class.getSimpleName(), {entity}.class);
        return q.getResultList();
    }}

    public {entity} persist({entity} e) {{
        em.persist(e);
        return e;
    }}

    public {entity} update({entity} e) {{
        return em.merge(e);
    }}

    public void delete(Long id) {{
        {entity} e = em.find({entity}.class, id);
        if (e != null) em.remove(e);
    }}
}}
"""


RESOURCE_TEMPLATE = '''package {pkg}.resources;

import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.inject.Inject;
import java.util.*;
import {pkg}.entities.{entity};
import {pkg}.repositories.{entity}Repository;

@Path("/{path}")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class {entity}Resource {{

    @Inject
    {entity}Repository repo;

    @GET
    public List<{entity}> list() {{
        return repo.listAll();
    }}

    @GET
    @Path("/{{id}}")
    public {entity} get(@PathParam("id") Long id) {{
        {entity} e = repo.find(id);
        if (e == null) throw new NotFoundException();
        return e;
    }}

    @POST
    public Response create({entity} e) {{
        repo.persist(e);
        return Response.status(Response.Status.CREATED).entity(e).build();
    }}

    @PUT
    @Path("/{{id}}")
    public {entity} update(@PathParam("id") Long id, {entity} e) {{
        e.setId(id);
        {entity} updated = repo.update(e);
        return updated;
    }}

    @DELETE
    @Path("/{{id}}")
    public void delete(@PathParam("id") Long id) {{
        repo.delete(id);
    }}
}}
'''


POM_XML = '''<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{group}</groupId>
  <artifactId>{artifact}</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <quarkus.platform.group-id>io.quarkus</quarkus.platform.group-id>
    <quarkus.platform.artifact-id>quarkus-bom</quarkus.platform.artifact-id>
    <quarkus.platform.version>3.3.2.Final</quarkus.platform.version>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>$${{quarkus.platform.group-id}}</groupId>
        <artifactId>$${{quarkus.platform.artifact-id}}</artifactId>
        <version>$${{quarkus.platform.version}}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>io.quarkus</groupId>
      <artifactId>quarkus-resteasy-jackson</artifactId>
    </dependency>
    <dependency>
      <groupId>io.quarkus</groupId>
      <artifactId>quarkus-hibernate-orm</artifactId>
    </dependency>
    <dependency>
      <groupId>io.quarkus</groupId>
      <artifactId>quarkus-jdbc-postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>jakarta.annotation</groupId>
      <artifactId>jakarta.annotation-api</artifactId>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>io.quarkus</groupId>
        <artifactId>quarkus-maven-plugin</artifactId>
        <version>$${{quarkus.platform.version}}</version>
        <executions>
          <execution>
            <goals>
              <goal>build</goal>
            </goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
'''


APPLICATION_PROPS = '''# Quarkus datasource (PostgreSQL) - replace values
quarkus.datasource.db-kind=postgresql
quarkus.datasource.username=youruser
quarkus.datasource.password=yourpassword
quarkus.datasource.jdbc.url=jdbc:postgresql://localhost:5432/yourdb

# Hibernate
quarkus.hibernate-orm.database.generation=update
'''

README = '''Generated Quarkus JPA project

How to build:
  mvn package

Run dev mode:
  mvn quarkus:dev

Edit src/main/resources/application.properties to configure Postgres.
'''

# ----------------------- Putting it all together -----------------------

def generate(project_root: Path, base_pkg: str, entities: Dict[str, Dict], relations: List[Dict]):
    group = base_pkg
    artifact = project_root.name

    src_main = project_root / 'src' / 'main' / 'java'
    pkg_path = src_main / Path(*base_pkg.split('.'))
    entities_path = pkg_path / 'entities'
    repos_path = pkg_path / 'repositories'
    resources_path = pkg_path / 'resources'

    mkdirp(entities_path)
    mkdirp(repos_path)
    mkdirp(resources_path)
    mkdirp(project_root / 'src' / 'main' / 'resources')

    rel_objs = [decide_relation_type(r) for r in relations]

    entity_extra_imports = {name: set() for name in entities}
    entity_rel_snippets: Dict[str, List[str]] = {name: [] for name in entities}

    for r in rel_objs:
        if r['type'] == 'OneToMany':
            one = r['one']
            many = r['many']
            fk_field = to_camel(one)
            snippet_many = f"    @ManyToOne\n    @JoinColumn(name=\"{to_snake(one)}_id\")\n    private {one} {fk_field};"
            entity_rel_snippets[many].append(snippet_many)
            entity_extra_imports[many].update({'jakarta.persistence.ManyToOne', 'jakarta.persistence.JoinColumn'})
            col_field = to_camel(many) + 'List'
            snippet_one = f"    @OneToMany(mappedBy=\"{fk_field}\")\n    private List<{many}> {col_field} = new ArrayList<>();"
            entity_rel_snippets[one].append(snippet_one)
            entity_extra_imports[one].update({'java.util.List', 'java.util.ArrayList', 'jakarta.persistence.OneToMany'})

        elif r['type'] == 'OneToOne':
            a = r['a']; b = r['b']
            a_field = to_camel(b)
            b_field = to_camel(a)
            snippet_a = f"    @OneToOne(mappedBy=\"{b_field}\")\n    private {b} {a_field};"
            snippet_b = f"    @OneToOne\n    @JoinColumn(name=\"{to_snake(a)}_id\")\n    private {a} {b_field};"
            entity_rel_snippets[a].append(snippet_a)
            entity_rel_snippets[b].append(snippet_b)
            entity_extra_imports[a].update({'jakarta.persistence.OneToOne'})
            entity_extra_imports[b].update({'jakarta.persistence.OneToOne', 'jakarta.persistence.JoinColumn'})

        elif r['type'] == 'ManyToMany':
            a = r['a']; b = r['b']
            a_field = to_camel(b) + 'List'
            b_field = to_camel(a) + 'List'
            snippet_a = f"    @ManyToMany\n    @JoinTable(name=\"{to_snake(a)}_{to_snake(b)}\",\n        joinColumns=@JoinColumn(name=\"{to_snake(a)}_id\"),\n        inverseJoinColumns=@JoinColumn(name=\"{to_snake(b)}_id\"))\n    private List<{b}> {a_field} = new ArrayList<>();"
            snippet_b = f"    @ManyToMany(mappedBy=\"{a_field}\")\n    private List<{a}> {b_field} = new ArrayList<>();"
            entity_rel_snippets[a].append(snippet_a)
            entity_rel_snippets[b].append(snippet_b)
            entity_extra_imports[a].update({'jakarta.persistence.ManyToMany','jakarta.persistence.JoinTable','jakarta.persistence.JoinColumn','java.util.List','java.util.ArrayList'})
            entity_extra_imports[b].update({'jakarta.persistence.ManyToMany','java.util.List','java.util.ArrayList'})

    for ename, meta in entities.items():
        attrs = meta['attrs']
        id_attr = None
        for a in attrs:
            if a[0].lower() == 'id' or a[0].startswith('*'):
                id_attr = a
                break
        if id_attr is None and attrs:
            id_attr = attrs[0]

        fields_lines = []
        getters_setters = []
        extra_imports = set()

        for aname, atype in attrs:
            jtype = java_type(atype)
            field_name = aname.strip()
            if id_attr and field_name == id_attr[0]:
                fields_lines.append('    @Id')
                fields_lines.append('    @GeneratedValue(strategy = GenerationType.IDENTITY)')
                extra_imports.update({'jakarta.persistence.Id','jakarta.persistence.GeneratedValue','jakarta.persistence.GenerationType'})
            fields_lines.append(f'    private {jtype} {field_name};')
            cap = field_name[0].upper() + field_name[1:]

            getters_setters.append(
                f"    public {jtype} get{cap}() {{\n"
                f"        return this.{field_name};\n"
                f"    }}"
            )

            setters = (
                f"    public void set{cap}({jtype} {field_name}) {{\n"
                f"        this.{field_name} = {field_name};\n"
                f"    }}"
            )
            
            getters_setters.append(setters)
            if '.' in jtype:
                extra_imports.add(jtype)

        rel_snips = '\n\n'.join(entity_rel_snippets.get(ename, []))
        if id_attr:
            pass

        imports_block = '\n'.join([f'import {imp};' for imp in sorted(extra_imports)])
        class_content = ENTITY_TEMPLATE.format(
            pkg=base_pkg,
            extra_imports=imports_block,
            table_name=to_snake(ename),
            class_name=ename,
            fields='\n'.join(fields_lines),
            relations=rel_snips,
            getters_setters='\n\n'.join(getters_setters)
        )
        fp = entities_path / f"{ename}.java"
        fp.write_text(class_content)

    for ename in entities:
        repo_content = REPOSITORY_TEMPLATE.format(pkg=base_pkg, entity=ename)
        (repos_path / f"{ename}Repository.java").write_text(repo_content)

    for ename in entities:
        path = to_snake(ename)
        res_content = RESOURCE_TEMPLATE.format(pkg=base_pkg, entity=ename, path=path)
        (resources_path / f"{ename}Resource.java").write_text(res_content)

    (project_root / 'pom.xml').write_text(POM_XML.format(group=group, artifact=artifact))
    (project_root / 'src' / 'main' / 'resources' / 'application.properties').write_text(APPLICATION_PROPS)
    (project_root / 'README.md').write_text(README)

    print(f"Project generated at: {project_root}")


# --------------------------- CLI --------------------------------------

def main():
    if len(sys.argv) < 4:
        print("Usage: python parser.py input.puml output_dir base.package")
        sys.exit(1)
    puml_file = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    base_pkg = sys.argv[3]

    if not puml_file.exists():
        print("Input file not found:", puml_file)
        sys.exit(1)

    if out_dir.exists():
        print("Warning: output dir exists, contents may be overwritten")

    text = puml_file.read_text(encoding='utf-8')
    entities = parse_entities(text)
    relations_raw = parse_relations(text)

    generate(out_dir, base_pkg, entities, relations_raw)

if __name__ == '__main__':
    main()
