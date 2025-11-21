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
