#!/usr/bin/env python3
"""
PUML -> Quarkus generator
"""

from pathlib import Path
import re
import sys
import textwrap
from typing import Dict, List
import random


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

DEFAULT_ENTITY_TPL = '''
package {package}.entities;

import jakarta.persistence.*;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.util.Set;
import java.util.HashSet;
{extra_imports}

{lombok_annotations}
@Entity
@Table(name = "{class_name_lower}")
public class {ClassName} {{

    {fields}

    {getters_setters}

}}
'''

DEFAULT_REPO_TPL = '''
package {pkg}.repositories;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import {pkg}.entities.{entity};

import java.util.List;

@ApplicationScoped
public class {entity}Repository {{

    @Inject
    EntityManager em;

    public List<{entity}> listAll() {{
        return em.createQuery("select e from {entity} e", {entity}.class).getResultList();
    }}

    public {entity} findById(Long id) {{
        return em.find({entity}.class, id);
    }}

    @Transactional
    public {entity} persist({entity} e) {{
        em.persist(e);
        return e;
    }}

    @Transactional
    public {entity} update({entity} e) {{
        return em.merge(e);
    }}

    @Transactional
    public void delete(Long id) {{
        em.createQuery("delete from {entity} e where e.id = :id")
            .setParameter("id", id)
            .executeUpdate();
    }}
}}
'''

DEFAULT_RESOURCE_TPL = '''
package {package}.resources;

import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import {package}.entities.{Entity};
import {package}.repositories.{Entity}Repository;

@Path("/{entities}")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class {Entity}Resource {{

    @Inject
    {Entity}Repository {entity}Repository;

    @GET
    public Response list() {{
        return Response.ok({entity}Repository.listAll()).build();
    }}

    @GET
    @Path("/{{id}}")
    public Response get(@PathParam("id") Long id) {{
        {Entity} e = {entity}Repository.findById(id);
        if (e == null) throw new NotFoundException();
        return Response.ok(e).build();
    }}

    @POST
    public Response create({Entity} e) {{
        {entity}Repository.persist(e);
        return Response.status(Response.Status.CREATED).entity(e).build();
    }}

    @PUT
    @Path("/{{id}}")
    public Response update(@PathParam("id") Long id, {Entity} e) {{
        e.setId(id);
        return Response.ok({entity}Repository.update(e)).build();
    }}

    @DELETE
    @Path("/{{id}}")
    public Response delete(@PathParam("id") Long id) {{
        {entity}Repository.delete(id);
        return Response.ok().build();
    }}
}}

'''

DEFAULT_POM_TPL = '''
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>

        <maven.compiler.release>21</maven.compiler.release>
        <compiler-plugin.version>3.14.1</compiler-plugin.version>

        <quarkus.platform.group-id>io.quarkus.platform</quarkus.platform.group-id>
        <quarkus.platform.artifact-id>quarkus-bom</quarkus.platform.artifact-id>
        <quarkus.platform.version>3.29.4</quarkus.platform.version>

        <surefire-plugin.version>3.5.4</surefire-plugin.version>
        <skipITs>true</skipITs>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>${{quarkus.platform.group-id}}</groupId>
                <artifactId>${{quarkus.platform.artifact-id}}</artifactId>
                <version>${{quarkus.platform.version}}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>

        {lombok_dependency}

        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-hibernate-orm</artifactId>
        </dependency>

        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-jdbc-postgresql</artifactId>
        </dependency>

        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-rest-jackson</artifactId>
        </dependency>

        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-arc</artifactId>
        </dependency>

        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-rest</artifactId>
        </dependency>

        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-junit5</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.rest-assured</groupId>
            <artifactId>rest-assured</artifactId>
            <scope>test</scope>
        </dependency>

    </dependencies>

    <build>
        <plugins>

            <plugin>
                <groupId>${{quarkus.platform.group-id}}</groupId>
                <artifactId>quarkus-maven-plugin</artifactId>
                <version>${{quarkus.platform.version}}</version>
                <extensions>true</extensions>
                <executions>
                    <execution>
                        <goals>
                            <goal>build</goal>
                            <goal>generate-code</goal>
                            <goal>generate-code-tests</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${{compiler-plugin.version}}</version>
                <configuration>
                    <release>21</release>

                    {lombok_processor}

                </configuration>
            </plugin>

        </plugins>
    </build>

</project>
'''

DEFAULT_APP_TPL = '''
# replace values !!!!!!!
quarkus.datasource.db-kind=postgresql
quarkus.datasource.devservices.port=5320
quarkus.http.port=8080
'''

DEFAULT_README = '''
Generated Quarkus JPA project (from PUML)

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

def render_entity(base_pkg: str, name: str, meta: Dict, relations: List[Dict], tpl: str, use_lombok: bool = False) -> str:
    attrs = meta["attrs"]
    
    fields = []
    getters_setters = []
    relation_fields = []

    extra_imports = []

    # Lombok
    lombok_annotations = ""
    if use_lombok:
        extra_imports.append("import lombok.Getter;")
        extra_imports.append("import lombok.Setter;")
        extra_imports.append("import lombok.Builder;")
        extra_imports.append("import lombok.NoArgsConstructor;")
        extra_imports.append("import lombok.AllArgsConstructor;")
        lombok_annotations = "@Getter\n@Setter\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor"

    # ------------------ normal fields ------------------
    for aname, atype in attrs:
        if aname.lower() == "id":
            fields.append("    @Id\n    @GeneratedValue\n    private Long id;")
            if not use_lombok:
                getters_setters.append(textwrap.dedent("""
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

        if not use_lombok:
            cap = aname[0].upper() + aname[1:]
            getters_setters.append(textwrap.dedent(f"""
                public {jtype} get{cap}() {{ return {aname}; }}
                public void set{cap}({jtype} {aname}) {{ this.{aname} = {aname}; }}
            """))

    # ------------------ relations ------------------
    for r in relations:
        if r["type"] == "OneToMany" and r["one"] == name:
            many = r["many"]
            field = to_camel(many) + "s"
            mapped_by = to_camel(name)
            relation_fields.append(textwrap.dedent(f"""
                @JsonIgnore
                @OneToMany(mappedBy = "{mapped_by}")
                private Set<{many}> {field} = new HashSet<>();
            """))

        if r["type"] == "OneToMany" and r["many"] == name:
            one = r["one"]
            camel = to_camel(one)
            relation_fields.append(textwrap.dedent(f"""
                @JsonIgnore
                @ManyToOne
                @JoinColumn(name = "{one.lower()}_id")
                private {one} {camel};
            """))

        if r["type"] == "ManyToMany":
            a, b = r["a"], r["b"]
            if a == name:
                other = b
                field = to_camel(other) + "s"
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
            elif b == name:
                other = a
                field = to_camel(other) + "s"
                mapped_by = to_camel(name) + "s"
                relation_fields.append(textwrap.dedent(f"""
                    @JsonIgnore
                    @ManyToMany(mappedBy = "{mapped_by}")
                    private Set<{other}> {field} = new HashSet<>();
                """))

    final = tpl.format(
        package=base_pkg,
        ClassName=name,
        fields="\n".join(fields + relation_fields),
        getters_setters="\n".join(getters_setters),
        extra_imports="\n".join(extra_imports),
        lombok_annotations=lombok_annotations,
        class_name_lower=name.lower()
    )

    return final


# ------------------ Main generator ------------------

def generate_import_sql(entities, relations):
    """
    Generiert INSERT Statements für alle Entities mit festen IDs (1,2,3...),
    inkl. Foreign Keys und ManyToMany Tabellen.
    """
    sql_lines = []
    id_counters = {ename: 1 for ename in entities}

    fk_map = {}
    for r in relations:
        if r['type'] == 'OneToMany':
            fk_map[r['many']] = r['one']

    for ename, meta in entities.items():
        for i in range(1, 2):
            columns = []
            values = []

            for attr, typ in meta["attrs"]:
                if attr.lower() == "id":
                    columns.append("id")
                    values.append(str(id_counters[ename]))
                    continue

                if ename in fk_map and attr.lower() == f"{fk_map[ename].lower()}_id":
                    columns.append(attr)
                    values.append("1")
                    continue

                columns.append(attr)
                if typ.lower() in ["string", "varchar", "text"]:
                    values.append(f"'{ename}_{i}'")
                elif typ.lower() in ["int", "integer"]:
                    values.append(str(random.randint(1, 100)))
                elif typ.lower() in ["double", "float"]:
                    values.append(str(round(random.uniform(1.0, 100.0), 2)))
                else:
                    values.append("NULL")

            sql_lines.append(f"INSERT INTO {ename.lower()} ({', '.join(columns)}) VALUES ({', '.join(values)});")
            id_counters[ename] += 1

    for r in relations:
        if r['type'] == 'ManyToMany':
            a, b = r['a'].lower(), r['b'].lower()
            join_table = f"{a}_{b}"
            sql_lines.append(f"INSERT INTO {join_table} ({a}_id, {b}_id) VALUES (1, 1);")

    return "\n".join(sql_lines)

def generate_pom_xml(project_root: Path, base_pkg: str, artifact: str, tpl: str, use_lombok: bool):

    lombok_dep = ""
    lombok_ap = ""

    if use_lombok:
        lombok_dep = textwrap.dedent("""
            <dependency>
                <groupId>org.projectlombok</groupId>
                <artifactId>lombok</artifactId>
                <version>1.18.42</version>
                <scope>provided</scope>
            </dependency>
        """).rstrip()

        lombok_ap = textwrap.dedent("""
            <annotationProcessorPaths>
                <path>
                    <groupId>org.projectlombok</groupId>
                    <artifactId>lombok</artifactId>
                    <version>1.18.42</version>
                </path>
            </annotationProcessorPaths>
        """).rstrip()

    pom = tpl.format(
        group_id=base_pkg,
        artifact_id=artifact,
        version="1.0.0-SNAPSHOT",
        lombok_dependency=lombok_dep,
        lombok_processor=lombok_ap
    )

    (project_root / "pom.xml").write_text(pom)

def load_template(tpl_dir: Path, name: str, default: str) -> str:
    f = tpl_dir / name
    if not f.exists():
        f.write_text(default)
    return f.read_text()


def generate(project_root: Path, base_pkg: str, entities: Dict[str, Dict], relations_raw: List[Dict], tpl_dir: Path, use_lombok:bool):
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
        code = render_entity(base_pkg, ename, meta, rel_objs, entity_tpl, use_lombok=use_lombok)
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


    rel_objs = [decide_relation(r) for r in relations_raw]

    # pom + app + readme
    group = base_pkg
    artifact = project_root.name
    
    generate_pom_xml(
        project_root=project_root,
        base_pkg=group,
        artifact=artifact,
        tpl=pom_tpl,
        use_lombok=use_lombok
    )

    (project_root / 'src' / 'main' / 'resources' / 'application.properties').write_text(app_tpl)
    (project_root / 'src' / 'main' / 'resources' / 'import.sql').write_text(generate_import_sql(entities=entities, relations=rel_objs))
    (project_root / 'README.md').write_text(readme_tpl)

    print(f"Project generated at: {project_root}")

# ------------------ CLI ------------------

def main():
    # Expected:
    # python puml_to_quarkus_generator.py input.puml output_dir base.package [--lombok]

    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print('Usage: python puml_to_quarkus_generator.py input.puml output_dir base.package [--lombok]')
        sys.exit(1)

    puml = Path(sys.argv[1])
    out = Path(sys.argv[2])
    base_pkg = sys.argv[3]

    use_lombok = False
    if len(sys.argv) == 5:
        if sys.argv[4] == "--lombok":
            use_lombok = True
        else:
            print("Error: Unknown option:", sys.argv[4])
            print('Usage: python puml_to_quarkus_generator.py input.puml output_dir base.package [--lombok]')
            sys.exit(1)

    if not puml.exists():
        print('Input PUML not found:', puml)
        sys.exit(1)

    tpl_dir = ensure_templates_dir(Path(__file__).parent)

    text = puml.read_text(encoding='utf-8')
    entities = parse_entities(text)
    relations_raw = parse_relations(text)

    generate(out, base_pkg, entities, relations_raw, tpl_dir, use_lombok=use_lombok)

    if use_lombok:
        print("Project generated with Lombok support")
    else:
        print("Project generated without Lombok (classic getters/setters)")


if __name__ == '__main__':
    main()

