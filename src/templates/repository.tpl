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

    @Transactional
    public List<{entity}> findAll() {{
        return em.createQuery("select e from {entity} e", {entity}.class).getResultList();
    }}

    @Transactional
    public {entity} findById(Long id) {{
        return em.find({entity}.class, id);
    }}

    @Transactional
    public {entity} save({entity} e) {{
        return em.merge(e);
    }}

    @Transactional
    public void deleteById(Long id) {{
        em.createQuery("delete from {entity} where id = :id")
            .setParameter("id", id)
            .executeUpdate();
    }}
}}
