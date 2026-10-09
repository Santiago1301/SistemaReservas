import { useMutation, useQuery } from '@apollo/client/react';
import { useEffect, useMemo, useState } from 'react';
import { dinero, duracion, mensajeDe, noches } from '../formato.js';
import { DESTINOS, DISPONIBILIDAD, RESERVAR } from '../graphql.js';

const PASOS_DE_FALLO = [
  ['', 'Ninguno (camino exitoso)'],
  ['VUELO', 'Reserva del vuelo'],
  ['HOTEL', 'Reserva del hotel'],
  ['AUTO', 'Reserva del auto'],
  ['PAGO', 'Cobro'],
];

function Opcion({ elegida, alElegir, titulo, detalle, precio, unidad }) {
  return (
    <button type="button" className={`opcion ${elegida ? 'elegida' : ''}`} onClick={alElegir} aria-pressed={elegida}>
      <span className="opcion-texto">
        <strong>{titulo}</strong>
        <small>{detalle}</small>
      </span>
      <span className="opcion-precio">
        {dinero(precio)}
        <small>{unidad}</small>
      </span>
    </button>
  );
}

export default function Buscar({ usuario }) {
  const [formulario, setFormulario] = useState({
    destino: 'Cartagena de Indias',
    fechaInicio: '2026-11-06',
    fechaFin: '2026-11-09',
    pasajeros: 1,
  });
  const [viaje, setViaje] = useState(null); // la búsqueda enviada
  const [eleccion, setEleccion] = useState({ vueloId: null, hotelId: null, autoId: null });
  const [simularFalloEn, setSimularFalloEn] = useState('');
  const [errorReserva, setErrorReserva] = useState(null);

  const destinos = useQuery(DESTINOS);
  const busqueda = useQuery(DISPONIBILIDAD, { variables: viaje, skip: !viaje, fetchPolicy: 'network-only' });
  const [reservar, reserva] = useMutation(RESERVAR);
  const oferta = viaje ? busqueda.data?.disponibilidad : null;

  // Al llegar resultados se preselecciona el paquete más económico que calculó el gateway.
  useEffect(() => {
    const paquete = oferta?.paqueteMasEconomico;
    setEleccion({
      vueloId: paquete?.vuelo.id ?? null,
      hotelId: paquete?.hotel.id ?? null,
      autoId: paquete?.auto.id ?? null,
    });
  }, [oferta]);

  // Una clave por combinación elegida: un doble clic en "Reservar" envía la misma
  // clave y el backend devuelve la orden original en vez de crear otra.
  const claveIdempotencia = useMemo(
    () => crypto.randomUUID(),
    [eleccion.vueloId, eleccion.hotelId, eleccion.autoId, simularFalloEn, viaje],
  );

  const vuelo = oferta?.vuelos.find((v) => v.id === eleccion.vueloId);
  const hotel = oferta?.hoteles.find((h) => h.id === eleccion.hotelId);
  const auto = oferta?.autos.find((a) => a.id === eleccion.autoId);
  const completo = vuelo && hotel && auto;
  const n = viaje ? noches(viaje.fechaInicio, viaje.fechaFin) : 0;
  const total = completo ? vuelo.precioCop * viaje.pasajeros + (hotel.precioNocheCop + auto.precioDiaCop) * n : 0;

  const cambiar = (campo) => (evento) => setFormulario({ ...formulario, [campo]: evento.target.value });

  function buscar(evento) {
    evento.preventDefault();
    setErrorReserva(null);
    setViaje({ ...formulario, pasajeros: Number(formulario.pasajeros) });
  }

  async function confirmar() {
    setErrorReserva(null);
    try {
      const { data } = await reservar({
        variables: {
          input: {
            vueloId: vuelo.id,
            hotelId: hotel.id,
            autoId: auto.id,
            fechaInicio: viaje.fechaInicio,
            fechaFin: viaje.fechaFin,
            pasajeros: viaje.pasajeros,
            claveIdempotencia,
            simularFalloEn: simularFalloEn || null,
          },
        },
      });
      window.location.hash = `#/orden/${data.reservarPaquete.id}`;
    } catch (fallo) {
      setErrorReserva(mensajeDe(fallo));
    }
  }

  return (
    <>
      <section className="tarjeta">
        <h1>Arma tu paquete</h1>
        <p className="subtitulo">Vuelo desde Bogotá, hotel y auto en una sola reserva.</p>
        <form className="buscador" onSubmit={buscar}>
          <label>
            Destino
            <select value={formulario.destino} onChange={cambiar('destino')}>
              {(destinos.data?.destinos ?? [formulario.destino]).map((d) => <option key={d}>{d}</option>)}
            </select>
          </label>
          <label>
            Ida
            <input type="date" value={formulario.fechaInicio} onChange={cambiar('fechaInicio')} required />
          </label>
          <label>
            Regreso
            <input type="date" value={formulario.fechaFin} onChange={cambiar('fechaFin')} min={formulario.fechaInicio} required />
          </label>
          <label>
            Pasajeros
            <input type="number" min="1" max="5" value={formulario.pasajeros} onChange={cambiar('pasajeros')} required />
          </label>
          <button className="boton" disabled={busqueda.loading}>{busqueda.loading ? 'Buscando…' : 'Buscar'}</button>
        </form>
      </section>

      {busqueda.error && <p className="aviso error">{mensajeDe(busqueda.error)}</p>}

      {oferta && (
        <>
          {!oferta.paqueteMasEconomico && (
            <p className="aviso">
              No hay un paquete completo para esa búsqueda. El catálogo actual tiene vuelos para el 6 de noviembre de 2026.
            </p>
          )}

          <div className="columnas">
            <section className="tarjeta">
              <h2>Vuelos <small>{oferta.vuelos.length}</small></h2>
              {oferta.vuelos.map((v) => (
                <Opcion
                  key={v.id}
                  elegida={v.id === eleccion.vueloId}
                  alElegir={() => setEleccion({ ...eleccion, vueloId: v.id })}
                  titulo={`${v.aerolinea} · ${v.horaSalida} → ${v.horaLlegada}`}
                  detalle={`${duracion(v.duracionMin)} · ${v.escalas ? `${v.escalas} escala(s)` : 'Directo'} · ${v.cuposDisponibles} cupos`}
                  precio={v.precioCop}
                  unidad="por persona"
                />
              ))}
              {!oferta.vuelos.length && <p className="vacio">Sin vuelos para esa fecha.</p>}
            </section>

            <section className="tarjeta">
              <h2>Hoteles <small>{oferta.hoteles.length}</small></h2>
              {oferta.hoteles.map((h) => (
                <Opcion
                  key={h.id}
                  elegida={h.id === eleccion.hotelId}
                  alElegir={() => setEleccion({ ...eleccion, hotelId: h.id })}
                  titulo={h.nombre}
                  detalle={[
                    h.estrellas && `${h.estrellas} estrellas`,
                    h.puntuacion && `${h.puntuacion.toFixed(1)}/5`,
                    h.servicios.slice(0, 2).join(', '),
                  ].filter(Boolean).join(' · ') || 'Sin detalles'}
                  precio={h.precioNocheCop}
                  unidad="por noche"
                />
              ))}
              {!oferta.hoteles.length && <p className="vacio">Sin hoteles disponibles.</p>}
            </section>

            <section className="tarjeta">
              <h2>Autos <small>{oferta.autos.length}</small></h2>
              {oferta.autos.map((a) => (
                <Opcion
                  key={a.id}
                  elegida={a.id === eleccion.autoId}
                  alElegir={() => setEleccion({ ...eleccion, autoId: a.id })}
                  titulo={a.modelo}
                  detalle={`${a.categoria} · ${a.proveedor} · ${a.unidadesDisponibles} unidades`}
                  precio={a.precioDiaCop}
                  unidad="por día"
                />
              ))}
              {!oferta.autos.length && <p className="vacio">Sin autos disponibles.</p>}
            </section>
          </div>

          {completo && (
            <section className="tarjeta resumen">
              <div>
                <h2>Tu paquete</h2>
                <p>
                  {vuelo.aerolinea} {vuelo.horaSalida} · {hotel.nombre} · {auto.modelo}
                </p>
                <p className="subtitulo">
                  {viaje.pasajeros} pasajero(s) · {n} noche(s)
                </p>
              </div>
              <div className="resumen-accion">
                <label className="demo">
                  Simular fallo en (demostración)
                  <select value={simularFalloEn} onChange={(e) => setSimularFalloEn(e.target.value)}>
                    {PASOS_DE_FALLO.map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
                  </select>
                </label>
                <strong className="total">{dinero(total)}</strong>
                {usuario ? (
                  <button className="boton" onClick={confirmar} disabled={reserva.loading}>
                    {reserva.loading ? 'Creando orden…' : 'Reservar paquete'}
                  </button>
                ) : (
                  <a className="boton" href="#/acceso">Inicia sesión para reservar</a>
                )}
              </div>
              {errorReserva && <p className="aviso error ancho">{errorReserva}</p>}
            </section>
          )}
        </>
      )}
    </>
  );
}
