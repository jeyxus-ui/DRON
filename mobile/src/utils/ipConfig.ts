import RNFS from 'react-native-fs';

const CONFIG_FILE = `${RNFS.DocumentDirectoryPath}/GCS/config.json`;
const DEFAULT_IP = '172.20.10.2';
const DEFAULT_MAX_ALT = 100;

let cachedIp: string | null = null;

export const getStoredIp = async (): Promise<string> => {
  if (cachedIp) return cachedIp;
  try {
    const exists = await RNFS.exists(CONFIG_FILE);
    if (!exists) return DEFAULT_IP;
    const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
    const parsed = JSON.parse(data);
    cachedIp = parsed.hostIp || DEFAULT_IP;
    return cachedIp!;
  } catch {
    return DEFAULT_IP;
  }
};

export const saveIp = async (ip: string): Promise<void> => {
  try {
    await RNFS.mkdir(`${RNFS.DocumentDirectoryPath}/GCS`);
    const exists = await RNFS.exists(CONFIG_FILE);
    let config: Record<string, any> = {};
    if (exists) {
      const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
      try { config = JSON.parse(data); } catch {}
    }
    config.hostIp = ip;
    await RNFS.writeFile(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf8');
    cachedIp = ip;
  } catch { /* fallback silencioso */ }
};

export const getDefaultIp = (): string => DEFAULT_IP;

export const getStoredMaxAltitude = async (): Promise<number> => {
  try {
    const exists = await RNFS.exists(CONFIG_FILE);
    if (!exists) return DEFAULT_MAX_ALT;
    const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
    const parsed = JSON.parse(data);
    return parsed.maxAltitude ?? DEFAULT_MAX_ALT;
  } catch {
    return DEFAULT_MAX_ALT;
  }
};

export const saveMaxAltitude = async (alt: number): Promise<void> => {
  await RNFS.mkdir(`${RNFS.DocumentDirectoryPath}/GCS`);
  try {
    const exists = await RNFS.exists(CONFIG_FILE);
    let config: Record<string, unknown> = {};
    if (exists) {
      const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
      config = JSON.parse(data);
    }
    config.maxAltitude = alt;
    await RNFS.writeFile(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf8');
  } catch {
    const data = JSON.stringify({ maxAltitude: alt }, null, 2);
    await RNFS.writeFile(CONFIG_FILE, data, 'utf8');
  }
};
