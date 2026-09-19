import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import ATComposer from './routes/ATComposer';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ATComposer />
  </StrictMode>
);
