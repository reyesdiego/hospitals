import Axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';

export const API_BASE_URL = 'http://localhost:8000';

export const axiosInstance: AxiosInstance = Axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const TOKEN_KEY = 'hosp_auth_token';

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// El token de sesion es lo unico que se manda: el rol y los permisos los resuelve la API.
axiosInstance.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const customInstance = <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig,
): Promise<T> => {
  const merged = {
    ...config,
    ...options,
    headers: {
      ...config.headers,
      ...options?.headers,
    },
  };
  const source = Axios.CancelToken.source();
  const promise = axiosInstance({
    ...merged,
    cancelToken: source.token,
  }).then(({ data }) => data as T);

  // @ts-expect-error cancel is added for react-query compatibility
  promise.cancel = () => source.cancel('Request cancelled');

  return promise;
};

export default customInstance;
