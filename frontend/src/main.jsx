import { ApolloProvider } from '@apollo/client/react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { cliente } from './apollo.js';
import App from './App.jsx';
import './estilos.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ApolloProvider client={cliente}>
      <App />
    </ApolloProvider>
  </StrictMode>,
);
