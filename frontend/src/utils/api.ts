import axios from "axios";

const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_BASE?.trim() || "http://127.0.0.1:8000/api",
  withCredentials: false,
});

export default api;
