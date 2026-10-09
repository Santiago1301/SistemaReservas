import { useQuery } from '@apollo/client/react';
import { dinero, fecha, mensajeDe } from '../formato.js';
import { MIS_ORDENES } from '../graphql.js';

export default function MisOrdenes({ usuario, cargandoUsuario }) {
  const { data, error, loading } = useQuery(MIS_ORDENES, { skip: !usuario, fetchPolicy: 'network-only' });

  if (!usuario) {
    return (
      <p className="aviso">
        {cargandoUsuario ? 'Cargando…' : <>Debes <a href="#/acceso">iniciar sesión</a> para ver tus órdenes.</>}
      </p>
    );
  }
  if (error) return <p className="aviso error">{mensajeDe(error)}</p>;
  if (loading) return <p className="aviso">Cargando tus órdenes…</p>;

  const ordenes = data?.misOrdenes ?? [];
  return (
    <section className="tarjeta">
      <h1>Mis órdenes</h1>
      {ordenes.length === 0 && <p className="vacio">Todavía no has reservado ningún paquete.</p>}
      <ul className="lista-ordenes">
        {ordenes.map((orden) => (
          <li key={orden.id}>
            <a href={`#/orden/${orden.id}`}>
              <span className={`etiqueta ${orden.estado.toLowerCase()}`}>{orden.estado}</span>
              <span className="lista-texto">
                <strong>{orden.hotel.ciudad}</strong>
                <small>
                  {orden.vuelo.aerolinea} · {orden.hotel.nombre} · {fecha(orden.fechaInicio)} – {fecha(orden.fechaFin)}
                </small>
              </span>
              <strong>{dinero(orden.totalCop)}</strong>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
