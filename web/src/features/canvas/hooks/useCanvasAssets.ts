import { useCallback, useEffect, useState } from "react";
import { listAssets, uploadAsset } from "../../../api/client";
import type { Asset } from "../../../types";

export function useCanvasAssets() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [kindFilter, setKindFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const result = await listAssets(kindFilter || undefined);
      setAssets(result);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load assets");
    } finally {
      setIsLoading(false);
    }
  }, [kindFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const upload = useCallback(async (file: File) => {
    let kind = "document";
    if (file.type.startsWith("image/")) kind = "image";
    else if (file.type.startsWith("audio/")) kind = "audio";
    else if (file.type.startsWith("video/")) kind = "video";

    setIsUploading(true);
    try {
      const asset = await uploadAsset(kind, file);
      setAssets((prev) => [asset, ...prev.filter((item) => item.id !== asset.id)]);
      return asset;
    } finally {
      setIsUploading(false);
    }
  }, []);

  return {
    assets,
    kindFilter,
    setKindFilter,
    isLoading,
    isUploading,
    error,
    refresh,
    upload,
  };
}
