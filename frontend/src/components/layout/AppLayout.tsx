import * as React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { ShoppingBag, Package, LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen w-full bg-background">
      <header className="border-b border-border bg-card">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold tracking-tight flex items-center gap-2">
              <ShoppingBag className="w-5 h-5 text-primary" />
              Fast Store
            </span>
            <nav className="flex items-center gap-5 text-sm">
              <NavLink
                to="/products"
                className={({ isActive }) =>
                  cn("transition-colors", isActive ? "text-primary font-medium" : "text-muted-foreground hover:text-foreground")
                }
              >
                Products
              </NavLink>
              <NavLink
                to="/orders"
                className={({ isActive }) =>
                  cn("transition-colors flex items-center gap-1", isActive ? "text-primary font-medium" : "text-muted-foreground hover:text-foreground")
                }
              >
                <Package className="w-3.5 h-3.5" />
                My Orders
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground hidden sm:inline">{user?.name}</span>
            <button
              onClick={handleLogout}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Log out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
