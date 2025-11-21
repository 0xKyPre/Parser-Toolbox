package {package}.entities;

import jakarta.persistence.*;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.util.Set;
import java.util.HashSet;

@Entity
public class {ClassName} {{

    @Id
    @GeneratedValue
    private Long id;

{fields}

{relationFields}

{getters}

{relationMethods}

}}
