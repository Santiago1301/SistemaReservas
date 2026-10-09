import { useMutation } from '@apollo/client/react';
import { useState } from 'react';
import { cliente } from '../apollo.js';
import { mensajeDe } from '../formato.js';
import { INICIAR_SESION, REGISTRAR } from '../graphql.js';

export default function Acceso() {
  const [modo, setModo] = useState('entrar'); // 'entrar' | 'registro'
  const [campos, setCampos] = useState({ email: '', nombre: '', contrasena: '' });
  const [error, setError] = useState(null);
  const [iniciarSesion, entrando] = useMutation(INICIAR_SESION);
  const [registrar, registrando] = useMutation(REGISTRAR);
  const ocupado = entrando.loading || registrando.loading;

  const cambiar = (campo) => (evento) => setCampos({ ...campos, [campo]: evento.target.value });

  async function enviar(evento) {
    evento.preventDefault();
    setError(null);
    try {
      if (modo === 'entrar') {
        await iniciarSesion({ variables: { email: campos.email, contrasena: campos.contrasena } });
      } else {
        await registrar({ variables: campos });
      }
      await cliente.resetStore(); // vuelve a pedir `me` ya con la sesión nueva
      window.location.hash = '#/buscar';
    } catch (fallo) {
      setError(mensajeDe(fallo));
    }
  }

  return (
    <section className="tarjeta angosta">
      <div className="pestanas">
        <button className={modo === 'entrar' ? 'activo' : ''} onClick={() => setModo('entrar')}>Iniciar sesión</button>
        <button className={modo === 'registro' ? 'activo' : ''} onClick={() => setModo('registro')}>Crear cuenta</button>
      </div>

      <form onSubmit={enviar} className="formulario">
        {modo === 'registro' && (
          <label>
            Nombre
            <input value={campos.nombre} onChange={cambiar('nombre')} required minLength={2} maxLength={80} autoComplete="name" />
          </label>
        )}
        <label>
          Correo
          <input type="email" value={campos.email} onChange={cambiar('email')} required autoComplete="email" />
        </label>
        <label>
          Contraseña
          <input
            type="password"
            value={campos.contrasena}
            onChange={cambiar('contrasena')}
            required
            minLength={modo === 'registro' ? 10 : 1}
            autoComplete={modo === 'registro' ? 'new-password' : 'current-password'}
          />
          {modo === 'registro' && <small>Mínimo 10 caracteres.</small>}
        </label>

        {error && <p className="aviso error">{error}</p>}
        <button className="boton" disabled={ocupado}>
          {ocupado ? 'Enviando…' : modo === 'entrar' ? 'Entrar' : 'Crear cuenta'}
        </button>
      </form>
    </section>
  );
}
