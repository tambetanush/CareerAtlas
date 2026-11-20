import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Cpu, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  type LlmProvider,
  getLlmProviders,
  loadLlmSettings,
  saveLlmSettings,
  testLlmConnection,
} from "@/lib/api";

const LABELS: Record<LlmProvider, string> = {
  anthropic: "Claude (Anthropic)",
  gemini: "Gemini (Google)",
  groq: "Groq",
  openai_compatible: "Local / OpenAI-compatible (Ollama, LM Studio)",
};

const DEFAULT = "server-default";

export function AiProviderPanel() {
  const { data } = useQuery({ queryKey: ["llm-providers"], queryFn: getLlmProviders, staleTime: 5 * 60 * 1000 });
  const saved = loadLlmSettings();
  const [provider, setProvider] = useState<string>(saved?.provider ?? DEFAULT);
  const [model, setModel] = useState(saved?.model ?? "");
  const [baseUrl, setBaseUrl] = useState(saved?.base_url ?? "");
  const [apiKey, setApiKey] = useState(saved?.api_key ?? "");
  const [testing, setTesting] = useState(false);

  const info = data?.providers.find((p) => p.id === provider);
  const isLocal = provider === "openai_compatible";
  const needsOwnKey = !!info && !info.server_key && !isLocal;

  const persist = () => {
    if (provider === DEFAULT) {
      saveLlmSettings(null);
      return;
    }
    saveLlmSettings({
      provider: provider as LlmProvider,
      model: model.trim() || undefined,
      base_url: isLocal ? baseUrl.trim() || undefined : undefined,
      api_key: apiKey.trim() || undefined,
    });
  };

  const onSave = () => {
    persist();
    toast.success("AI provider saved", { description: "Used for your next requests on this device." });
  };

  const onTest = async () => {
    persist();
    setTesting(true);
    try {
      const r = await testLlmConnection();
      toast.success(`Connected to ${LABELS[r.provider] ?? r.provider}`, { description: `Model ${r.model} replied: "${r.reply}"` });
    } catch (err: any) {
      toast.error("Connection failed", { description: err?.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="hover-lift rounded-3xl border border-border bg-card p-6 shadow-soft sm:p-8">
      <div className="flex items-center gap-2">
        <Cpu className="h-5 w-5 text-primary" />
        <h2 className="font-display text-xl font-semibold">AI provider</h2>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Choose which model runs the agents for you. Leave it on the default to use CareerAtlas's own setup
        {data?.default ? ` (${LABELS[data.default] ?? data.default})` : ""}.
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="llm-provider">Provider</Label>
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger id="llm-provider" className="rounded-xl">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT}>CareerAtlas default</SelectItem>
              {(data?.providers ?? []).map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {LABELS[p.id]}
                  {p.server_key ? "" : p.id === "openai_compatible" ? "" : " — your key"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {provider !== DEFAULT && (
          <div className="space-y-1.5">
            <Label htmlFor="llm-model">Model</Label>
            <Input
              id="llm-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={info?.default_model ?? ""}
              className="rounded-xl"
            />
            {!isLocal && !apiKey && (
              <p className="text-xs text-muted-foreground">With CareerAtlas's key the default model is used.</p>
            )}
          </div>
        )}

        {isLocal && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="llm-base-url">Base URL</Label>
            <Input
              id="llm-base-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434/v1"
              className="rounded-xl"
            />
            <p className="text-xs text-muted-foreground">
              A model on your own computer only works when you run CareerAtlas locally; the hosted site can't reach it.
            </p>
          </div>
        )}

        {provider !== DEFAULT && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="llm-key">API key {needsOwnKey ? "(required)" : "(optional)"}</Label>
            <Input
              id="llm-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="rounded-xl"
            />
            <p className="text-xs text-muted-foreground">
              Stored only in this browser and sent with each request. CareerAtlas never saves it.
            </p>
          </div>
        )}
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <Button onClick={onSave} className="rounded-full">
          <Check className="mr-1 h-4 w-4" /> Save
        </Button>
        <Button onClick={onTest} variant="outline" disabled={testing} className="rounded-full">
          {testing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
          Test connection
        </Button>
      </div>
    </section>
  );
}
