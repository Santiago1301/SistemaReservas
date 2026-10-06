-- 001 · Esquema inicial de WanderSync
-- Regla de diseño: cada microservicio es dueño de sus tablas. Solo hay llaves
-- foráneas entre tablas del mismo servicio; entre servicios se guarda el id
-- "suelto" y la consistencia la garantiza la SAGA, no la base de datos.

begin;

-- GraphQL nativo de Supabase: genera el esquema GraphQL a partir de las tablas.
create extension if not exists pg_graphql;

-- Nombres en camelCase en GraphQL (precio_cop -> precioCop) sin cambiar las columnas.
comment on schema public is '@graphql({"inflect_names": true})';


-- ===================================================================
-- USUARIOS (dueño: gateway)
-- ===================================================================
create table usuarios (
  id               uuid primary key default gen_random_uuid(),
  email            text not null unique check (email = lower(email)),
  nombre           text not null,
  hash_contrasena  text not null,            -- Argon2id; nunca la contraseña en claro
  creado_en        timestamptz not null default now()
);


-- ===================================================================
-- CATÁLOGO (lo escribe la ingesta con Dask; lo leen todos)
-- La restricción "unique" de cada tabla permite que la ingesta actualice
-- un registro existente en vez de duplicarlo (upsert).
-- El inventario (cupos, habitaciones, unidades) es un valor inicial asignado
-- por el sistema: las fuentes no lo publican.
-- ===================================================================
create table vuelos (
  id                 uuid primary key default gen_random_uuid(),
  origen             text not null,          -- código IATA, p. ej. BOG
  destino            text not null,          -- código IATA, p. ej. CTG
  fecha_salida       date not null,
  hora_salida        time not null,
  hora_llegada       time not null,
  aerolinea          text not null,
  duracion_min       integer check (duracion_min > 0),
  escalas            integer not null default 0 check (escalas >= 0),
  precio_cop         integer not null check (precio_cop >= 0),
  cupos_disponibles  integer not null default 5 check (cupos_disponibles >= 0),
  fuente             text not null,
  extraido_en        timestamptz not null default now(),
  unique (origen, destino, fecha_salida, aerolinea, hora_salida)
);
create index vuelos_ruta_idx on vuelos (origen, destino, fecha_salida);

create table hoteles (
  id                        uuid primary key default gen_random_uuid(),
  nombre                    text not null,
  ciudad                    text not null,
  estrellas                 smallint check (estrellas between 1 and 5),
  puntuacion                numeric(2,1) check (puntuacion between 0 and 5),
  precio_noche_cop          integer not null check (precio_noche_cop >= 0),
  servicios                 text[] not null default '{}',
  habitaciones_disponibles  integer not null default 5 check (habitaciones_disponibles >= 0),
  fuente                    text not null,
  extraido_en               timestamptz not null default now(),
  unique (nombre, ciudad)
);
create index hoteles_ciudad_idx on hoteles (ciudad);

create table autos (
  id                    uuid primary key default gen_random_uuid(),
  ciudad                text not null,
  proveedor             text not null,
  modelo                text not null,
  categoria             text not null,
  precio_dia_cop        integer not null check (precio_dia_cop >= 0),
  unidades_disponibles  integer not null default 5 check (unidades_disponibles >= 0),
  fuente                text not null,
  extraido_en           timestamptz not null default now(),
  unique (ciudad, proveedor, modelo)
);
create index autos_ciudad_idx on autos (ciudad);


-- ===================================================================
-- ÓRDENES Y FACTURACIÓN (dueño: servicio de órdenes)
-- ===================================================================
create table ordenes (
  id                  uuid primary key default gen_random_uuid(),
  usuario_id          uuid not null,          -- id de otro servicio: sin llave foránea
  vuelo_id            uuid not null,
  hotel_id            uuid not null,
  auto_id             uuid not null,
  fecha_inicio        date not null,
  fecha_fin           date not null check (fecha_fin > fecha_inicio),
  pasajeros           integer not null default 1 check (pasajeros > 0),
  total_cop           integer not null check (total_cop >= 0),
  estado              text not null default 'PENDIENTE'
                      check (estado in ('PENDIENTE', 'CONFIRMADA', 'COMPENSANDO', 'CANCELADA')),
  motivo_fallo        text,
  -- Para la demo: obliga a fallar un paso y así ver las compensaciones.
  simular_fallo_en    text check (simular_fallo_en in ('VUELO', 'HOTEL', 'AUTO', 'PAGO')),
  -- Un doble clic envía la misma clave y no crea una segunda orden.
  clave_idempotencia  uuid not null unique,
  flow_run_id         text,                   -- ejecución de Prefect que corre la SAGA
  creado_en           timestamptz not null default now(),
  actualizado_en      timestamptz not null default now()
);
create index ordenes_usuario_idx on ordenes (usuario_id, creado_en desc);

create table pagos (
  id              uuid primary key default gen_random_uuid(),
  orden_id        uuid not null unique references ordenes (id),
  monto_cop       integer not null check (monto_cop >= 0),
  estado          text not null check (estado in ('COBRADO', 'REEMBOLSADO')),
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

-- Bitácora de la SAGA: una fila por cada paso y por cada compensación.
create table saga_pasos (
  id         bigint generated always as identity primary key,
  orden_id   uuid not null references ordenes (id),
  paso       text not null,                   -- VUELO, HOTEL, AUTO, PAGO
  tipo       text not null check (tipo in ('ACCION', 'COMPENSACION')),
  estado     text not null check (estado in ('OK', 'FALLO')),
  detalle    text,
  creado_en  timestamptz not null default now()
);
create index saga_pasos_orden_idx on saga_pasos (orden_id, id);


-- ===================================================================
-- RESERVAS (una tabla por servicio dueño)
-- "orden_id unique": si Prefect reintenta un paso, el servicio encuentra la
-- reserva ya hecha y no reserva dos veces (idempotencia).
-- ===================================================================
create table reservas_vuelo (
  id              uuid primary key default gen_random_uuid(),
  orden_id        uuid not null unique,
  vuelo_id        uuid not null references vuelos (id),
  pasajeros       integer not null check (pasajeros > 0),
  estado          text not null check (estado in ('RESERVADA', 'CANCELADA')),
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create table reservas_hotel (
  id              uuid primary key default gen_random_uuid(),
  orden_id        uuid not null unique,
  hotel_id        uuid not null references hoteles (id),
  fecha_entrada   date not null,
  fecha_salida    date not null check (fecha_salida > fecha_entrada),
  estado          text not null check (estado in ('RESERVADA', 'CANCELADA')),
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create table reservas_auto (
  id                uuid primary key default gen_random_uuid(),
  orden_id          uuid not null unique,
  auto_id           uuid not null references autos (id),
  fecha_recogida    date not null,
  fecha_devolucion  date not null check (fecha_devolucion > fecha_recogida),
  estado            text not null check (estado in ('RESERVADA', 'CANCELADA')),
  creado_en         timestamptz not null default now(),
  actualizado_en    timestamptz not null default now()
);


-- ===================================================================
-- SEGURIDAD: Row Level Security activada y sin políticas.
-- Con la clave pública no se puede leer ni escribir ninguna tabla; solo el
-- backend, que usa la clave secreta o la conexión directa, tiene acceso.
-- ===================================================================
alter table usuarios        enable row level security;
alter table vuelos          enable row level security;
alter table hoteles         enable row level security;
alter table autos           enable row level security;
alter table ordenes         enable row level security;
alter table pagos           enable row level security;
alter table saga_pasos      enable row level security;
alter table reservas_vuelo  enable row level security;
alter table reservas_hotel  enable row level security;
alter table reservas_auto   enable row level security;

commit;
