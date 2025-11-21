#!/usr/bin/env python3
"""
PUML -> Quarkus generator

Usage:
  python puml_to_quarkus_generator.py input.puml output_dir base.package

This script will ensure a `templates/` folder exists next to the script with default
templates (if missing it creates them). Then it parses the PlantUML file and
renders Java files into the output directory.

Templates are simple Python .format() templates. Java literal braces are escaped
as `{{`/`}}` in the templates so .format() works correctly. Maven `${...}`
occurrences are escaped as `$${{...}}` so pom generation works.

Generated entity style:
 - package {pkg}.entities
 - uses `Collection<T>` for to-many relations
 - getters/setters as in the examples you provided
 - ManyToOne setter keeps bidirectional collections in sync when possible

"""

from pathlib import Path
import re
import sys
import textwrap
from typing import Dict, List

# ------------------ Utility functions ------------------

def to_camel(s: str) -> str:
    if not s:
        return s
    return s[0].lower() + s[1:]


def to_snake(s: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()


def ensure_templates_dir(base: Path) -> Path:
    tpl_dir = base / 'templates'
    tpl_dir.mkdir(exist_ok=True)
    return tpl_dir

# ------------------ Default templates ------------------

DEFAULT_ENTITY_TPL = '''package {pkg}.entities;

import jakarta.persistence.*;
{extra_imports}

@Entity
@Table(name = "{table_name}")
public class {class_name} {{

{fields}

{relations}

{getters_setters}

}}'''

DEFAULT_REPO_TPL = '''package {pkg}.repositories;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import {pkg}.entities.{entity};
import java.util.Collection;

@ApplicationScoped
public class {entity}Repository {{

    @Inject
    EntityManager em;

    public {entity} find(Long id) {{
        return em.find({entity}.class, id);
    }}

    public Collection<{entity}> listAll() {{
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

}}'''

DEFAULT_RESOURCE_TPL = '''package {pkg}.resources;

import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.inject.Inject;
import java.util.Collection;

import {pkg}.entities.{entity};
import {pkg}.repositories.{entity}Repository;

@Path("/{path}")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class {entity}Resource {{

    @Inject
    {entity}Repository repo;

    @GET
    public Collection<{entity}> list() {{
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
        return repo.update(e);
    }}

    @DELETE
    @Path("/{{id}}")
    public void delete(@PathParam("id") Long id) {{
        repo.delete(id);
    }}

}}'''

DEFAULT_POM_TPL = '''<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
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

DEFAULT_APP_TPL = '''# Quarkus datasource (PostgreSQL) - replace values
quarkus.datasource.db-kind=postgresql
quarkus.datasource.username=youruser
quarkus.datasource.password=yourpassword
quarkus.datasource.jdbc.url=jdbc:postgresql://localhost:5432/yourdb

# Hibernate
quarkus.hibernate-orm.database.generation=update
'''

DEFAULT_README = '''Generated Quarkus JPA project (from PUML)

How to build:
  mvn package

Run dev mode:
  mvn quarkus:dev

Edit src/main/resources/application.properties to configure Postgres.
'''

# ------------------ Parser (simple, robust) ------------------

ENTITY_RE = re.compile(r"(?:entity|class)\s+(\w+)\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
RELATION_RE = re.compile(r"^\s*(\w+)\s*([<>\|o{}]+-{2,}>|-{2,}[<>\|o{}]+)\s*(\w+)(?:\s*:\s*(.*))?$")


def parse_entities(text: str) -> Dict[str, Dict]:
    entities = {}
    for m in ENTITY_RE.finditer(text):
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
            if not aname:
                continue
            attrs.append((aname, atype))
        entities[name] = {'name': name, 'attrs': attrs}
    return entities


def parse_relations(text: str) -> List[Dict]:
    relations = []
    for raw in text.splitlines():
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


def detect_mult(token: str) -> str:
    if '|' in token:
        return 'ONE'
    if '{' in token or '}' in token:
        return 'MANY'
    if 'o' in token and ('{' in token or '}' in token):
        return 'MANY'
    return 'UNKNOWN'


def decide_relation(rel: Dict) -> Dict:
    lt = detect_mult(rel['left_token'])
    rt = detect_mult(rel['right_token'])
    left = rel['left']
    right = rel['right']
    if lt == 'ONE' and rt == 'MANY':
        return {'type': 'OneToMany', 'one': left, 'many': right}
    if lt == 'MANY' and rt == 'ONE':
        return {'type': 'OneToMany', 'one': right, 'many': left}
    if lt == 'ONE' and rt == 'ONE':
        return {'type': 'OneToOne', 'a': left, 'b': right}
    if lt == 'MANY' and rt == 'MANY':
        return {'type': 'ManyToMany', 'a': left, 'b': right}
    return {'type': 'OneToMany', 'one': left, 'many': right}

# ------------------ Renderer ------------------

def render_entity(base_pkg: str, name: str, meta: Dict, relations: List[Dict], tpl: str) -> str:
    attrs = meta["attrs"]
    
    fields = []
    getters = []
    relation_fields = []
    relation_methods = []

    # ------------------ normal fields ------------------
    for aname, atype in attrs:
        if aname.lower() == "id":
            fields.append("    @Id\n    @GeneratedValue\n    private Long id;")
            getters.append(textwrap.dedent("""
                public Long getId() { return id; }
                public void setId(Long id) { this.id = id; }
            """))
            continue

        jmap = {
            "string": "String",
            "int": "Integer",
            "integer": "Integer",
            "long": "Long",
            "double": "Double",
            "float": "Float",
            "boolean": "Boolean",
        }
        jtype = jmap.get(atype.lower(), atype)

        fields.append(f"    private {jtype} {aname};")

        cap = aname[0].upper() + aname[1:]
        getters.append(textwrap.dedent(f"""
            public {jtype} get{cap}() {{ return {aname}; }}
            public void set{cap}({jtype} {aname}) {{ this.{aname} = {aname}; }}
        """))

    # ------------------ relations ------------------
    for r in relations:
        # ONE TO MANY on inverse side
        if r["type"] == "OneToMany" and r["one"] == name:
            many = r["many"]
            field = many[0].lower() + many[1:] + "s"

            relation_fields.append(textwrap.dedent(f"""
                @JsonIgnore
                @OneToMany(mappedBy = "{name[0].lower()+name[1:]}")
                private Set<{many}> {field} = new HashSet<>();
            """))

            relation_methods.append(textwrap.dedent(f"""
                public Set<{many}> get{field.capitalize()}() {{ return {field}; }}
                public void set{field.capitalize()}(Set<{many}> s) {{ this.{field} = s; }}

                public void add{many}({many} e) {{
                    e.set{name}(this);
                }}

                public void remove{many}({many} e) {{
                    e.set{name}(null);
                }}
            """))

        # MANY TO ONE owning
        if r["type"] == "OneToMany" and r["many"] == name:
            one = r["one"]
            camel = one[0].lower() + one[1:]

            relation_fields.append(textwrap.dedent(f"""
                @JsonIgnore
                @ManyToOne
                @JoinColumn(name = "{one.lower()}_id")
                private {one} {camel};
            """))

            relation_methods.append(textwrap.dedent(f"""
                public {one} get{one}() {{ return {camel}; }}

                public void set{one}({one} g) {{
                    if (this.{camel} != null) {{
                        this.{camel}.get{name}s().remove(this);
                    }}
                    this.{camel} = g;
                    if (g != null) {{
                        g.get{name}s().add(this);
                    }}
                }}
            """))

        # MANY TO MANY
        if r["type"] == "ManyToMany":
            a, b = r["a"], r["b"]

            if a == name:
                # owning side
                other = b
                field = other[0].lower() + other[1:] + "s"

                relation_fields.append(textwrap.dedent(f"""
                    @JsonIgnore
                    @ManyToMany
                    @JoinTable(
                        name = "{name.lower()}_{other.lower()}",
                        joinColumns = @JoinColumn(name = "{name.lower()}_id"),
                        inverseJoinColumns = @JoinColumn(name = "{other.lower()}_id")
                    )
                    private Set<{other}> {field} = new HashSet<>();
                """))

                relation_methods.append(textwrap.dedent(f"""
                    public Set<{other}> get{field.capitalize()}() {{ return {field}; }}
                    public void set{field.capitalize()}(Set<{other}> s) {{ this.{field} = s; }}

                    public void add{other}({other} e) {{
                        e.get{name}s().add(this);
                        {field}.add(e);
                    }}

                    public void remove{other}({other} e) {{
                        e.get{name}s().remove(this);
                        {field}.remove(e);
                    }}
                """))

            elif b == name:
                # inverse side
                other = a
                field = other[0].lower() + other[1:] + "s"

                relation_fields.append(textwrap.dedent(f"""
                    @JsonIgnore
                    @ManyToMany(mappedBy = "{other[0].lower()+other[1:]}s")
                    private Set<{other}> {field} = new HashSet<>();
                """))

                relation_methods.append(textwrap.dedent(f"""
                    public Set<{other}> get{field.capitalize()}() {{ return {field}; }}
                    public void set{field.capitalize()}(Set<{other}> s) {{ this.{field} = s; }}
                """))

    final = tpl.format(
        package = base_pkg,
        ClassName = name,
        fields = "\n".join(fields),
        relationFields = "\n".join(relation_fields),
        getters = "\n".join(getters),
        relationMethods = "\n".join(relation_methods),
    )

    return final

# ------------------ Main generator ------------------

def load_template(tpl_dir: Path, name: str, default: str) -> str:
    f = tpl_dir / name
    if not f.exists():
        f.write_text(default)
    return f.read_text()


def generate(project_root: Path, base_pkg: str, entities: Dict[str, Dict], relations_raw: List[Dict], tpl_dir: Path):
    # prepare tree
    src_main = project_root / 'src' / 'main' / 'java'
    pkg_path = src_main / Path(*base_pkg.split('.'))
    entities_path = pkg_path / 'entities'
    repos_path = pkg_path / 'repositories'
    resources_path = pkg_path / 'resources'
    (entities_path).mkdir(parents=True, exist_ok=True)
    (repos_path).mkdir(parents=True, exist_ok=True)
    (resources_path).mkdir(parents=True, exist_ok=True)
    (project_root / 'src' / 'main' / 'resources').mkdir(parents=True, exist_ok=True)

    # load templates
    entity_tpl = load_template(tpl_dir, 'entity.tpl', DEFAULT_ENTITY_TPL)
    repo_tpl = load_template(tpl_dir, 'repository.tpl', DEFAULT_REPO_TPL)
    resource_tpl = load_template(tpl_dir, 'resource.tpl', DEFAULT_RESOURCE_TPL)
    pom_tpl = load_template(tpl_dir, 'pom.tpl', DEFAULT_POM_TPL)
    app_tpl = load_template(tpl_dir, 'application.properties.tpl', DEFAULT_APP_TPL)
    readme_tpl = load_template(tpl_dir, 'readme.tpl', DEFAULT_README)

    # decide relations
    rel_objs = [decide_relation(r) for r in relations_raw]

    # render entities
    for ename, meta in entities.items():
        code = render_entity(base_pkg, ename, meta, rel_objs, entity_tpl)
        (entities_path / f"{ename}.java").write_text(code)

    # repositories
    for ename in entities:
        r = repo_tpl.format(pkg=base_pkg, entity=ename)
        (repos_path / f"{ename}Repository.java").write_text(r)

    # resources
    for ename in entities:
        entity_lower = to_camel(ename)
        entities_lower = entity_lower + "s"

        res = resource_tpl.format(
            package=base_pkg,
            Entity=ename,
            entity=entity_lower,
            entities=entities_lower
        )

        (resources_path / f"{ename}Resource.java").write_text(res)


    # pom + app + readme
    group = base_pkg
    artifact = project_root.name
    (project_root / 'pom.xml').write_text(
        pom_tpl.format(
            group_id=group,
            artifact_id=artifact,
            version="1.0.0-SNAPSHOT"
        )
    )
    (project_root / 'src' / 'main' / 'resources' / 'application.properties').write_text(app_tpl)
    (project_root / 'README.md').write_text(readme_tpl)

    print(f"Project generated at: {project_root}")

# ------------------ CLI ------------------

def main():
    if len(sys.argv) < 4:
        print('Usage: python puml_to_quarkus_generator.py input.puml output_dir base.package')
        sys.exit(1)
    puml = Path(sys.argv[1])
    out = Path(sys.argv[2])
    base_pkg = sys.argv[3]

    if not puml.exists():
        print('Input PUML not found:', puml)
        sys.exit(1)

    tpl_dir = ensure_templates_dir(Path(__file__).parent)

    text = puml.read_text(encoding='utf-8')
    entities = parse_entities(text)
    relations_raw = parse_relations(text)

    generate(out, base_pkg, entities, relations_raw, tpl_dir)

if __name__ == '__main__':
    main()
