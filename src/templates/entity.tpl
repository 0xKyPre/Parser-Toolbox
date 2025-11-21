package {package}.entities;

import jakarta.persistence.*;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.util.Set;
import java.util.HashSet;

@Entity
public class {ClassName} {{
    {fields}

    {relationFields}

    {getters}

    {relationMethods}
}}
