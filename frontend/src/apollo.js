import { ApolloClient, HttpLink, InMemoryCache } from '@apollo/client';

// Toda la comunicación con el backend pasa por este único punto: el gateway GraphQL.
const URL_GATEWAY = import.meta.env.VITE_GATEWAY_URL ?? 'http://localhost:4000/graphql';

export const cliente = new ApolloClient({
  link: new HttpLink({
    uri: URL_GATEWAY,
    // Envía la cookie de sesión (HttpOnly) aunque el gateway esté en otro puerto.
    credentials: 'include',
  }),
  cache: new InMemoryCache(),
});
