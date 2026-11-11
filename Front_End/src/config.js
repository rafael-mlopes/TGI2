// URL base da API Flask. Pode ser definida no build pela variável VITE_API_URL
// (arquivo .env do Vite ou build-arg do Docker). Padrão: API local na porta 5000.
export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:5000').replace(/\/+$/, '')
