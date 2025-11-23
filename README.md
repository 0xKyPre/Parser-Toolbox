# Paser-Toolbox

A flexible tool for parsing PlantUML class diagrams and automatically generating:
- Java Entities
- Java Repositories
- Java REST Resources
- POM files, Quarkus project structure, etc.

## how to run the tool?

Syntax:
```
python parser.py <input.puml> <output_directory> <base_java_package> [--lombok]
```

For the test an example:
```
python parser.py ./../test/test.puml ./../test_folder/flower-pots  at.ac.htlleonding.wmctest5
```

This will:
- Parse test/test.puml
- Generate Java files inside ./output/
- Use the base Java package:

```cmd
at.ac.htlleonding.wmctest5.entities
at.ac.htlleonding.wmctest5.repositories
at.ac.htlleonding.wmctest5.resources
```

## lombok
with the flag `--lombok` you can generate a project with lombok. BUT you need sdk 21 for lombok probably or need to upgrade.  else you can use the sdk 25 without lombok without any problems too.

## project structure:
```cmd
Parser-Toolbox/
│
├── src/
│   ├── parser.py               # Main program
│   ├── templates/
│   │     ├── entity.tpl
│   │     ├── repository.tpl
│   │     ├── resource.tpl
│   │     └── pom.tpl
│
├── test/
│   └── test.puml               # Example PlantUML file
│
└── README.md

```

## License
MIT License - Free for personal and commercial use.