import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import DagViewer from "../components/DagViewer";
import LocalUploader from "../components/LocalUploader";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, LayoutTemplate } from "lucide-react";
import { toast } from "sonner";

const DagExplore = () => {
  const [searchParams] = useSearchParams();
  const [graphData, setGraphData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const backend = searchParams.get("backend") || "";
  const repoPath = searchParams.get("repo_path") || "";
  const cypherQuery = searchParams.get("cypher_query") || "";

  useEffect(() => {
    if (!backend && !cypherQuery) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const url = new URL("/api/graph", backend || window.location.origin);
        if (repoPath) url.searchParams.append("repo_path", repoPath);
        if (cypherQuery) url.searchParams.append("cypher_query", cypherQuery);

        const response = await fetch(url.toString());
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || `Server error (${response.status})`);
        }
        setGraphData(await response.json());
      } catch (err: any) {
        setError(err.message);
        toast.error("Failed to connect: " + err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [backend, repoPath, cypherQuery]);

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background">
        <Loader2 className="w-12 h-12 animate-spin text-purple-400 mb-4" />
        <p className="text-lg font-medium animate-pulse text-muted-foreground">
          Building DAG layout…
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background px-6 text-center">
        <h1 className="text-2xl font-bold mb-2 text-red-500">Connection Error</h1>
        <p className="text-muted-foreground max-w-md mb-8">{error}</p>
        <button onClick={() => window.location.reload()}
          className="bg-primary text-primary-foreground px-6 py-2 rounded-lg">
          Retry
        </button>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-background pt-24 pb-12 px-6 flex flex-col items-center">
      <AnimatePresence mode="wait">
        {!graphData ? (
          <motion.div
            key="uploader"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="w-full max-w-4xl mx-auto flex flex-col items-center mt-12"
          >
            <div className="text-center mb-12">
              <div className="inline-flex items-center gap-3 mb-4">
                <LayoutTemplate className="w-10 h-10 text-purple-400" />
                <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-purple-400 to-indigo-500 bg-clip-text text-transparent">
                  DAG Explorer
                </h1>
              </div>
              <p className="text-muted-foreground text-lg max-w-2xl mx-auto mt-2">
                Visualize your code as a <strong className="text-purple-300">layered architecture diagram</strong> — 
                Repository → Files → Classes → Functions, with clean routed edges. Like Mermaid, but interactive.
              </p>

              {/* Feature pills */}
              <div className="flex flex-wrap justify-center gap-2 mt-6">
                {["Dagre Layout Engine", "Top→Bottom or Left→Right", "Per-file focus mode", "Export as Mermaid", "Node type filtering"].map((f) => (
                  <span key={f} className="text-[11px] font-bold uppercase tracking-widest px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300">
                    {f}
                  </span>
                ))}
              </div>
            </div>

            <div className="w-full max-w-2xl">
              <LocalUploader onComplete={setGraphData} />
            </div>
          </motion.div>
        ) : (
          <DagViewer
            key="dag"
            data={graphData}
            onClose={() => setGraphData(null)}
          />
        )}
      </AnimatePresence>
    </main>
  );
};

export default DagExplore;
