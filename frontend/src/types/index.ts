export interface UserPublic {
  id: number;
  name: string;
  email: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface Product {
  id: number;
  name: string;
  price: number;
  description: string;
  image_url: string;
}

export interface ProductCreate {
  name: string;
  price: number;
  description?: string;
  image_url?: string;
  initial_stock?: number;
}

export interface ProductUpdate {
  name?: string;
  price?: number;
  description?: string;
  image_url?: string;
}

export interface Order {
  id: number;
  user_id: number;
  product_id: number;
  status: string;
  created_at: string;
}

export interface InventoryItem {
  product_id: number;
  stock: number;
}
