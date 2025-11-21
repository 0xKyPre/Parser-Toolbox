package {pkg}.repositories;

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

}}