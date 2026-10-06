import axios from "axios";
import type {
  UserPublic,
  LoginResponse,
  Product,
  ProductCreate,
  ProductUpdate,
  Order,
  InventoryItem,
} from "@/types";

// No base URL needed: the frontend is served by Traefik at the same origin
// as the API routes (/users, /products, /orders, /inventory), so every
// call below is relative.
export const api = axios.create({
  headers: { "Content-Type": "application/json" },
});

const TOKEN_KEY = "fast_store_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    return err.response?.data?.detail || err.message || "Something went wrong";
  }
  return "Something went wrong";
}

// ---------------- Auth ----------------

export const authApi = {
  register: (name: string, email: string, password: string) =>
    api.post<UserPublic>("/users/", { name, email, password }).then((r) => r.data),

  login: (email: string, password: string) =>
    api.post<LoginResponse>("/login", { email, password }).then((r) => r.data),

  me: () => api.get<UserPublic>("/users/me").then((r) => r.data),
};

// ---------------- Products ----------------

export const productsApi = {
  list: () => api.get<Product[]>("/products").then((r) => r.data),
  get: (id: number) => api.get<Product>(`/products/${id}`).then((r) => r.data),
  // All three admin-only (server enforces via require_admin - a non-admin
  // token gets 403 back regardless of what the UI shows).
  create: (payload: ProductCreate) =>
    api.post<Product & { initial_stock: number }>("/products", payload).then((r) => r.data),
  update: (id: number, payload: ProductUpdate) =>
    api.put<Product>(`/products/${id}`, payload).then((r) => r.data),
  remove: (id: number) =>
    api.delete<{ deleted: boolean; id: number }>(`/products/${id}`).then((r) => r.data),
};

// ---------------- Inventory ----------------

export const inventoryApi = {
  list: () => api.get<InventoryItem[]>("/inventory/").then((r) => r.data),
};

// ---------------- Orders ----------------

export const ordersApi = {
  place: (productId: number) =>
    api
      .post<{ message: string; order: Order }>("/orders/", null, {
        params: { product_id: productId },
      })
      .then((r) => r.data),

  mine: () => api.get<Order[]>("/orders/").then((r) => r.data),
};
