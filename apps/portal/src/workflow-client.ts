import { useMemo } from "react";
import { OpenClassWorkspaceClient } from "@openclass/sdk";
import { controlClient } from "./api";
import { useAuth } from "./auth";

export function useWorkflowClient() {
  const auth = useAuth();
  return useMemo(() => new OpenClassWorkspaceClient(controlClient, () => auth.token()), [auth]);
}
