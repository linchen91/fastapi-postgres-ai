import { createContext, useContext, useEffect, useState } from "react";

const ConfigContext = createContext(null);
export const useConfig = () => useContext(ConfigContext);

export function ConfigProvider({ children }) {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    fetch('/config.json')
    .then(res => res.json())
    .then(setConfig)
  }, []);

  if (!config)
    return <div className="text-center p-5">loading config ...</div>;

  return (
    <ConfigContext.Provider value={config}>
      {children}
    </ConfigContext.Provider>
  );
}
