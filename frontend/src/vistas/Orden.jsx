import { useQuery } from '@apollo/client/react';
import { useEffect } from 'react';
import { dinero, fecha, hora, mensajeDe } from '../formato.js';
import { ORDEN } from '../graphql.js';

const ETAPAS = [
  ['VUELO', 'Vuelo'],
  ['HOTEL', 'Hotel'],
  ['AUTO', 'Auto'],
  ['PAGO', 'Pago'],
];

const TEXTO_ESTADO = {
  PENDIENTE: 'Procesando la reserva…',
  CONFIRMADA: 'Reserva confirmada',
  COMPENSANDO: 'Algo falló: revirtiendo lo ya reservado…',
  CANCELADA: 'Reserva cancelada: todo fue revertido',
};

const ES_FINAL = (estado) => estado === 'CONFIRMADA' || estado === 'CANCELADA';

/** Resume en qué quedó una etapa a partir de la bitácora de la SAGA. */
function estadoDeEtapa(paso, pasos) {
  const accion = pasos.find((p) => p.paso === paso && p.tipo === 'ACCION');
  const compensacion = pasos.find((p) => p.paso === paso && p.tipo === 'COMPENSACION');
  if (!accion) return { clase: 'espera', texto: 'En espera' };
  if (accion.estado === 'FALLO') return { clase: 'fallo', texto: 'Falló' };
  if (compensacion) return { clase: 'compensado', texto: 'Revertido' };
  return { clase: 'ok', texto: 'Hecho' };
}

export default function Orden({ id, usuario, cargandoUsuario }) {
  // Se vuelve a consultar cada 2 segundos mientras la SAGA siga en curso.
  const { data, error, loading, stopPolling } = useQuery(ORDEN, {
    variables: { id },
    pollInterval: 2000,
    skip: !usuario,
    fetchPolicy: 'network-only',
  });
  const orden = data?.orden;

  useEffect(() => {
    if (orden && ES_FINAL(orden.estado)) stopPolling();
  }, [orden?.estado, stopPolling]);

  if (!usuario) {
    return (
      <p className="aviso">
        {cargandoUsuario ? 'Cargando…' : <>Debes <a href="#/acceso">iniciar sesión</a> para ver esta orden.</>}
      </p>
    );
  }
  if (error) return <p className="aviso error">{mensajeDe(error)}</p>;
  if (loading && !orden) return <p className="aviso">Cargando la orden…</p>;
  if (!orden) return <p className="aviso error">La orden no existe.</p>;

  return (
    <>
      <section className={`tarjeta estado-orden ${orden.estado.toLowerCase()}`}>
        <div>
          <span className="etiqueta">{orden.estado}</span>
          <h1>{TEXTO_ESTADO[orden.estado]}</h1>
          {orden.motivoFallo && <p className="motivo">{orden.motivoFallo}</p>}
        </div>
        <div className="estado-total">
          <strong className="total">{dinero(orden.totalCop)}</strong>
          <small>{orden.estadoPago ? `Pago: ${orden.estadoPago.toLowerCase()}` : 'Sin cobro'}</small>
        </div>
      </section>

      <section className="tarjeta">
        <h2>Etapas de la transacción</h2>
        <div className="etapas">
          {ETAPAS.map(([paso, nombre]) => {
            const etapa = estadoDeEtapa(paso, orden.pasos);
            return (
              <div key={paso} className={`etapa ${etapa.clase}`}>
                <strong>{nombre}</strong>
                <span>{etapa.texto}</span>
              </div>
            );
          })}
        </div>

        <h3>Bitácora de la SAGA</h3>
        {orden.pasos.length === 0 && <p className="vacio">Esperando el primer paso…</p>}
        <ol className="bitacora">
          {orden.pasos.map((p, i) => (
            <li key={i} className={p.estado === 'FALLO' ? 'fallo' : p.tipo === 'COMPENSACION' ? 'compensado' : 'ok'}>
              <time>{hora(p.creadoEn)}</time>
              <span className="tipo">{p.tipo === 'ACCION' ? 'Acción' : 'Compensación'}</span>
              <strong>{p.paso}</strong>
              <span>{p.estado}</span>
              {p.detalle && <small>{p.detalle}</small>}
            </li>
          ))}
        </ol>

        {orden.urlPrefect && (
          <a className="enlace" href={orden.urlPrefect} target="_blank" rel="noreferrer">
            Ver esta ejecución en el panel de Prefect ↗
          </a>
        )}
      </section>

      <section className="tarjeta">
        <h2>Paquete</h2>
        <dl className="detalle">
          <dt>Vuelo</dt>
          <dd>{orden.vuelo.aerolinea} · {orden.vuelo.origen} → {orden.vuelo.destino} · {orden.vuelo.horaSalida}</dd>
          <dt>Hotel</dt>
          <dd>{orden.hotel.nombre} · {orden.hotel.ciudad}</dd>
          <dt>Auto</dt>
          <dd>{orden.auto.modelo} · {orden.auto.proveedor}</dd>
          <dt>Fechas</dt>
          <dd>{fecha(orden.fechaInicio)} – {fecha(orden.fechaFin)} · {orden.pasajeros} pasajero(s)</dd>
        </dl>
      </section>
    </>
  );
}
