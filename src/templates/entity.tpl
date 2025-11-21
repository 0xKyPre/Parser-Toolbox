package {pkg}.entities;

import jakarta.persistence.*;
{extra_imports}

@Entity
@Table(name = "{table_name}")
public class {class_name} {{

{fields}

{relations}

{getters_setters}

}}