import { useEffect, useState } from 'react';
import { fetchMission } from '../services/api';
import type { Mission } from '../types';

export function useMission() {
  const [mission, setMission] = useState<Mission | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMission()
      .then((data) => setMission(data))
      .finally(() => setLoading(false));
  }, []);

  return { mission, setMission, loading };
}
