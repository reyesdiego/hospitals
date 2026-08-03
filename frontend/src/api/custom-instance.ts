import Axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';

export const API_BASE_URL = 'http://localhost:8000';

export const axiosInstance: AxiosInstance = Axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem('hosp_auth_token');
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
