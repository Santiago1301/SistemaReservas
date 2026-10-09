import { gql } from '@apollo/client';

// Cada operación pide solo los campos que su pantalla muestra.

export const ME = gql`
  query Me {
    me { id email nombre }
  }
`;

export const DESTINOS = gql`
  query Destinos {
    destinos
  }
`;

export const DISPONIBILIDAD = gql`
  query Disponibilidad($destino: String!, $fechaInicio: Date!, $fechaFin: Date!, $pasajeros: Int) {
    disponibilidad(destino: $destino, fechaInicio: $fechaInicio, fechaFin: $fechaFin, pasajeros: $pasajeros) {
      vuelos(limite: 8) { id aerolinea horaSalida horaLlegada duracionMin escalas precioCop cuposDisponibles }
      hoteles(limite: 8) { id nombre estrellas puntuacion precioNocheCop servicios habitacionesDisponibles }
      autos(limite: 8) { id modelo proveedor categoria precioDiaCop unidadesDisponibles }
      paqueteMasEconomico { noches totalCop vuelo { id } hotel { id } auto { id } }
    }
  }
`;

export const ORDEN = gql`
  query Orden($id: ID!) {
    orden(id: $id) {
      id estado totalCop motivoFallo fechaInicio fechaFin pasajeros estadoPago urlPrefect creadoEn
      vuelo { id aerolinea origen destino horaSalida horaLlegada }
      hotel { id nombre ciudad }
      auto { id modelo proveedor }
      pasos { paso tipo estado detalle creadoEn }
    }
  }
`;

export const MIS_ORDENES = gql`
  query MisOrdenes {
    misOrdenes {
      id estado totalCop fechaInicio fechaFin creadoEn
      vuelo { id aerolinea destino }
      hotel { id nombre ciudad }
    }
  }
`;

export const REGISTRAR = gql`
  mutation Registrar($email: String!, $nombre: String!, $contrasena: String!) {
    registrar(email: $email, nombre: $nombre, contrasena: $contrasena) { id email nombre }
  }
`;

export const INICIAR_SESION = gql`
  mutation IniciarSesion($email: String!, $contrasena: String!) {
    iniciarSesion(email: $email, contrasena: $contrasena) { id email nombre }
  }
`;

export const CERRAR_SESION = gql`
  mutation CerrarSesion {
    cerrarSesion
  }
`;

export const RESERVAR = gql`
  mutation ReservarPaquete($input: ReservaInput!) {
    reservarPaquete(input: $input) { id estado }
  }
`;
