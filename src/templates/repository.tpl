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
