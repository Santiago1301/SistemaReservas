# WanderSync Travel Solutions

Plataforma de empaquetamiento turístico dinámico: vuelo, hotel y auto en una sola reserva.
Parcial práctico del segundo corte de **Patrones Arquitectónicos Avanzados**.

| Requisito del parcial | Cómo se cumple |
|---|---|
| Docker Compose | 13 contenedores que levantan con `docker compose up` |
| GraphQL | API Gateway con Apollo Server; catálogo leído del GraphQL nativo de Supabase (`pg_graphql`) |
| Patrón SAGA | Orquestación en un flow de Prefect, con compensaciones automáticas |
| Dask | Scheduler y 2 workers que ejecutan el scraping y la carga en paralelo |
| Prefect | Flows de ingesta y de SAGA, con reintentos y panel de monitoreo |
| Ciberseguridad | Regeneración de sesión, Argon2id, límites de peticiones y auditoría de dependencias |

Documentación:

- [Documento técnico de arquitectura](docs/documento-tecnico.md): diagramas, SAGA, seguridad y decisiones.
- [Guion de la demostración](docs/guion-demo.md).
- [Reportes de auditoría de dependencias](docs/seguridad/auditoria).

## Requisitos

- Docker Desktop con al menos 4 GB de memoria asignados.
- Un proyecto de [Supabase](https://supabase.com) (plan gratuito).
- Conexión a internet (base de datos en la nube y scraping de fuentes reales).

## Configuración (una sola vez)

1. Copia el archivo de ejemplo y completa los valores desde el panel de Supabase:

   ```bash
   cp .env.example .env
   ```

   | Variable | Dónde se obtiene |
   |---|---|
   | `SUPABASE_URL` | Project Settings → API → Project URL |
   | `SUPABASE_PUBLISHABLE_KEY` | Project Settings → API Keys → Publishable key |
   | `SUPABASE_SECRET_KEY` | Project Settings → API Keys → Secret key |
   | `SUPABASE_DB_URL` | Botón Connect → **Session pooler** (incluye la contraseña de la base) |
   | `SESSION_SECRET` | Genéralo con `openssl rand -hex 32` |

2. Crea las tablas y activa `pg_graphql` en la base:

   ```bash
   docker run --rm -i --env-file .env postgres:17-alpine sh -c 'psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1' < db/migraciones/001_esquema_inicial.sql
   ```

## Arranque

```bash
docker compose up -d --build
```

La primera vez descarga y construye las imágenes (la de los workers incluye Chromium y pesa unos 4 GB).
Con las imágenes ya construidas, el sistema queda listo en unos dos minutos.

| Qué | Dirección |
|---|---|
| Aplicación web | http://localhost:3000 |
| Gateway GraphQL (Apollo Sandbox) | http://localhost:4000/graphql |
| Panel de Prefect | http://localhost:4200 |
| Panel de Dask | http://localhost:8787 |
| Fuente simulada de autos | http://localhost:8010 |
| Documentación de cada microservicio | http://localhost:8001/docs (vuelos), `8002` (hoteles), `8003` (autos), `8004` (órdenes) |

### Cargar el catálogo

La ingesta corre sola cada 2 horas. Para lanzarla en el momento:

```bash
docker compose exec flujos prefect deployment run ingesta/programada
```

También se puede lanzar desde el panel de Prefect: Deployments → `ingesta/programada` → Run.

Para levantar el sistema sin la ingesta automática (por ejemplo, para no consultar a Google mientras se desarrolla):

```bash
INGESTA_PAUSADA=true docker compose up -d
```

## Estructura

```
├── docker-compose.yml       los 13 contenedores
├── gateway/                 API Gateway GraphQL (Apollo Server, Node)
├── frontend/                React + Vite, servido por nginx
├── servicios/
│   ├── vuelos/              FastAPI: reserva y cancela cupos
│   ├── hoteles/             FastAPI: reserva y cancela habitaciones
│   ├── autos/               FastAPI: reserva y cancela vehículos
│   ├── ordenes/             FastAPI: órdenes, facturación y bitácora de la SAGA
│   └── fuente-autos/        sitio simulado de alquiler de autos (fuente de scraping)
├── flujos/                  Prefect + Dask
│   ├── ingesta.py           flow de scraping y carga
│   ├── saga.py              flow orquestador de la SAGA
│   ├── scraping/            extractores: Google Flights, Google Hotels, fuente de autos
│   ├── limpieza.py          validación y normalización
│   └── persistencia.py      carga en Supabase (upsert)
├── db/migraciones/          esquema de la base de datos
└── docs/                    documento técnico, guion, evidencias y auditorías
```

## Comandos útiles

```bash
docker compose ps                 # estado de los contenedores
docker compose logs -f gateway    # registros de un servicio
docker compose down               # apagar todo
```

## Auditoría de dependencias

Los reportes están en [docs/seguridad/auditoria](docs/seguridad/auditoria). Para repetirlos:

```bash
cd gateway && npm audit
cd frontend && npm audit
docker compose exec vuelos pip freeze > requisitos.txt && pip-audit -r requisitos.txt --no-deps --disable-pip
```
