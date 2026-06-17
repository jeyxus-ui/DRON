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
