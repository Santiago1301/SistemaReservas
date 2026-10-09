import { useMutation, useQuery } from '@apollo/client/react';
import { useEffect, useState } from 'react';
import { cliente } from './apollo.js';
import { CERRAR_SESION, ME } from './graphql.js';
import Acceso from './vistas/Acceso.jsx';
import Buscar from './vistas/Buscar.jsx';
import MisOrdenes from './vistas/MisOrdenes.jsx';
import Orden from './vistas/Orden.jsx';

/** Navegación mínima con el fragmento de la URL: #/buscar, #/orden/<id>, ... */
function useRuta() {
  const leer = () => window.location.hash.replace(/^#\/?/, '').split('/');
  const [ruta, setRuta] = useState(leer);
  useEffect(() => {
    const alCambiar = () => setRuta(leer());
    window.addEventListener('hashchange', alCambiar);
    return () => window.removeEventListener('hashchange', alCambiar);
  }, []);
  return ruta;
}

export default function App() {
  const [vista, parametro] = useRuta();
  const { data, loading } = useQuery(ME);
  const [cerrarSesion] = useMutation(CERRAR_SESION);
  const usuario = data?.me ?? null;

  async function salir() {
    await cerrarSesion();
    await cliente.resetStore(); // borra de la caché todo lo que era del usuario
    window.location.hash = '#/buscar';
  }

  let contenido;
  if (vista === 'acceso') contenido = <Acceso />;
  else if (vista === 'orden' && parametro) contenido = <Orden id={parametro} usuario={usuario} cargandoUsuario={loading} />;
  else if (vista === 'ordenes') contenido = <MisOrdenes usuario={usuario} cargandoUsuario={loading} />;
  else contenido = <Buscar usuario={usuario} />;

  return (
    <>
      <header className="cabecera">
        <a className="marca" href="#/buscar">WanderSync</a>
        <nav>
          <a href="#/buscar" className={vista === 'buscar' || !vista ? 'activo' : ''}>Buscar paquete</a>
          {usuario && <a href="#/ordenes" className={vista === 'ordenes' ? 'activo' : ''}>Mis órdenes</a>}
        </nav>
        <div className="sesion">
          {usuario ? (
            <>
              <span className="saludo">{usuario.nombre}</span>
              <button className="boton secundario" onClick={salir}>Cerrar sesión</button>
            </>
          ) : (
            !loading && <a className="boton" href="#/acceso">Iniciar sesión</a>
          )}
        </div>
      </header>
      <main>{contenido}</main>
    </>
  );
}
