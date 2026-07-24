import RNFS from 'react-native-fs';

const CONFIG_FILE = `${RNFS.DocumentDirectoryPath}/GCS/config.json`;
const DEFAULT_IP = '172.20.10.2';

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
  await RNFS.mkdir(`${RNFS.DocumentDirectoryPath}/GCS`);
  const data = JSON.stringify({ hostIp: ip }, null, 2);
  await RNFS.writeFile(CONFIG_FILE, data, 'utf8');
  cachedIp = ip;
};

export const getDefaultIp = (): string => DEFAULT_IP;

const DEFAULT_MAX_ALT = 3;

export const getMaxAltitude = async (): Promise<number> => {
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
  try {
    await RNFS.mkdir(`${RNFS.DocumentDirectoryPath}/GCS`);
    const exists = await RNFS.exists(CONFIG_FILE);
    let config: Record<string, any> = {};
    if (exists) {
      const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
      try { config = JSON.parse(data); } catch {}
    }
    config.maxAltitude = alt;
    await RNFS.writeFile(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf8');
  } catch { /* fallback silencioso */ }
};

const DEFAULT_MAX_SPEED = 0.3;

export const getMaxSpeed = async (): Promise<number> => {
  try {
    const exists = await RNFS.exists(CONFIG_FILE);
    if (!exists) return DEFAULT_MAX_SPEED;
    const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
    const parsed = JSON.parse(data);
    return parsed.maxSpeed ?? DEFAULT_MAX_SPEED;
  } catch {
    return DEFAULT_MAX_SPEED;
  }
};

export const saveMaxSpeed = async (spd: number): Promise<void> => {
  try {
    await RNFS.mkdir(`${RNFS.DocumentDirectoryPath}/GCS`);
    const exists = await RNFS.exists(CONFIG_FILE);
    let config: Record<string, any> = {};
    if (exists) {
      const data = await RNFS.readFile(CONFIG_FILE, 'utf8');
      try { config = JSON.parse(data); } catch {}
    }
    config.maxSpeed = spd;
    await RNFS.writeFile(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf8');
  } catch { /* fallback silencioso */ }
};
