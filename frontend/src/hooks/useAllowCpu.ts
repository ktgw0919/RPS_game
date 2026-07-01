import { useEffect, useState } from 'react';

import { getPublicConfig } from '@/lib/api';

let cachedAllowCpu: boolean | null = null;

/** Whether demo CPU players are enabled on the server (`ALLOW_CPU`). */
export function useAllowCpu(): boolean | null {
  const [allowCpu, setAllowCpu] = useState<boolean | null>(cachedAllowCpu);

  useEffect(() => {
    if (cachedAllowCpu !== null) {
      setAllowCpu(cachedAllowCpu);
      return;
    }

    let cancelled = false;
    void getPublicConfig()
      .then((config) => {
        cachedAllowCpu = config.allow_cpu;
        if (!cancelled) setAllowCpu(config.allow_cpu);
      })
      .catch(() => {
        if (!cancelled) setAllowCpu(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return allowCpu;
}
