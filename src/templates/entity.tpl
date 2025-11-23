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