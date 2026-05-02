import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { adminListStores } from "../api/client";

export interface StoreEntry {
  store_id: string;
  store_name: string;
  drive_folder_url: string;
  sync_enabled: boolean;
}

interface StoreContextValue {
  storeId: string;
  setStoreId: (id: string) => void;
  stores: StoreEntry[];
  storeName: string;
}

const StoreContext = createContext<StoreContextValue>({
  storeId: "",
  setStoreId: () => {},
  stores: [],
  storeName: "",
});

export function StoreProvider({ children }: { children: ReactNode }) {
  const [storeId, setStoreIdState] = useState<string>(() => localStorage.getItem("iris_store") ?? "");
  const [stores, setStores] = useState<StoreEntry[]>([]);

  useEffect(() => {
    adminListStores()
      .then((r) => setStores((r.data ?? []).map((s: any) => ({
        store_id: s.store_id,
        store_name: s.store_name,
        drive_folder_url: s.drive_folder_url ?? "",
        sync_enabled: Boolean(s.sync_enabled),
      }))))
      .catch(() => {});
  }, []);

  function setStoreId(id: string) {
    setStoreIdState(id);
    if (id) localStorage.setItem("iris_store", id);
    else localStorage.removeItem("iris_store");
  }

  const storeName = stores.find((s) => s.store_id === storeId)?.store_name ?? "";

  return (
    <StoreContext.Provider value={{ storeId, setStoreId, stores, storeName }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  return useContext(StoreContext);
}
