import { Combobox, Transition } from "@headlessui/react";
import { Check, ChevronsUpDown, Search, X } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

export interface StoreSelectOption {
  store_id: string;
  store_name?: string;
}

interface StoreSelectProps {
  stores: StoreSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  allLabel?: string;
  includeAll?: boolean;
  className?: string;
  disabled?: boolean;
}

function optionLabel(option: StoreSelectOption | undefined, allLabel: string) {
  if (!option) return "";
  if (!option.store_id) return allLabel;
  return option.store_name && option.store_name !== option.store_id
    ? `${option.store_name} (${option.store_id})`
    : option.store_id;
}

export default function StoreSelect({
  stores,
  value,
  onChange,
  placeholder = "Select store",
  allLabel = "All Stores",
  includeAll = false,
  className = "",
  disabled = false,
}: StoreSelectProps) {
  const [query, setQuery] = useState("");

  const options = useMemo(() => {
    const normalized = stores
      .map((store) => ({
        store_id: String(store.store_id || ""),
        store_name: String(store.store_name || store.store_id || ""),
      }))
      .sort((left, right) => optionLabel(left, allLabel).localeCompare(optionLabel(right, allLabel)));
    return includeAll ? [{ store_id: "", store_name: allLabel }, ...normalized] : normalized;
  }, [allLabel, includeAll, stores]);

  const selected = options.find((option) => option.store_id === value) ?? (includeAll ? options[0] : undefined);
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = normalizedQuery
    ? options.filter((option) =>
        `${option.store_name || ""} ${option.store_id}`.toLowerCase().includes(normalizedQuery)
      )
    : options;

  return (
    <Combobox
      value={value}
      onChange={(nextValue: string | null) => {
        onChange(nextValue ?? "");
        setQuery("");
      }}
      nullable
      disabled={disabled}
    >
      <div className={`relative ${className}`}>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Combobox.Input
            className="iris-input pl-9 pr-16"
            placeholder={placeholder}
            autoComplete="off"
            displayValue={() => optionLabel(selected, allLabel)}
            onChange={(event) => setQuery(event.target.value)}
          />
          {value && !disabled && (
            <button
              type="button"
              onClick={() => {
                onChange("");
                setQuery("");
              }}
              className="absolute right-9 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              aria-label="Clear store filter"
            >
              <X size={12} />
            </button>
          )}
          <Combobox.Button className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400">
            <ChevronsUpDown size={16} />
          </Combobox.Button>
        </div>

        <Transition
          as={Fragment}
          leave="transition ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
          afterLeave={() => setQuery("")}
        >
          <Combobox.Options className="absolute z-[260] mt-2 max-h-72 w-full overflow-auto rounded-xl border border-slate-200 bg-white py-2 shadow-2xl ring-1 ring-slate-200/60 focus:outline-none">
            {filtered.length === 0 ? (
              <div className="px-4 py-3 text-sm text-slate-400">No stores match your search.</div>
            ) : (
              filtered.map((option) => (
                <Combobox.Option
                  key={option.store_id || "__all__"}
                  value={option.store_id}
                  className={({ active }) =>
                    `relative cursor-pointer select-none px-4 py-2.5 pr-10 ${
                      active ? "bg-blue-50 text-blue-700" : "text-slate-700"
                    }`
                  }
                >
                  {({ selected: isSelected }) => (
                    <>
                      <div className="flex flex-col">
                        <span className={`text-sm ${isSelected ? "font-semibold" : "font-medium"}`}>
                          {option.store_name || option.store_id || allLabel}
                        </span>
                        {option.store_id ? (
                          <span className="text-xs text-slate-400">{option.store_id}</span>
                        ) : (
                          <span className="text-xs text-slate-400">Show all stores</span>
                        )}
                      </div>
                      {isSelected && (
                        <span className="absolute inset-y-0 right-3 flex items-center text-blue-600">
                          <Check size={14} />
                        </span>
                      )}
                    </>
                  )}
                </Combobox.Option>
              ))
            )}
          </Combobox.Options>
        </Transition>
      </div>
    </Combobox>
  );
}
