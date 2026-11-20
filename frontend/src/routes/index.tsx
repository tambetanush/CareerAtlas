import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ArrowUpRight, Compass, FileText, Sparkles, Map, MapPin, Target, Briefcase, Loader2 } from "lucide-react";
import { getPublicJobs } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ThemeSelector } from "@/components/theme-selector";
import { useAuth } from "@/context/auth-context";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "CareerAtlas — Find the path to your next role" },
      {
        name: "description",
        content:
          "Upload your resume, pick a target role, and get a personalized roadmap of skills, projects, and jobs — built for early-career engineers.",
      },
      { property: "og:title", content: "CareerAtlas — Find the path to your next role" },
      {
        property: "og:description",
        content:
          "A friendly career guide that turns your resume into a clear, week-by-week plan toward the role you want.",
      },
    ],
  }),
  component: Landing,
});

function Landing() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && user) {
      navigate({ to: "/dashboard" });
    }
  }, [loading, user, navigate]);

  // Signed-in (or still resolving) — don't flash the marketing page.
  if (loading || user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-hero">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-hero">
      {/* Top bar */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-soft">
            <Compass className="h-5 w-5" />
          </span>
          CareerAtlas
        </Link>
        <div className="flex items-center gap-2">
          <ThemeSelector />
          <Link to="/onboarding" className="hidden rounded-full px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground sm:inline-block">
            Sign in
          </Link>
          <Button asChild className="rounded-full bg-coral text-coral-foreground hover:bg-coral/90 shadow-warm">
            <Link to="/onboarding">Get started</Link>
          </Button>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 pb-20 pt-10 sm:px-6 sm:pt-16">
        <div className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-1.5 text-xs font-medium text-muted-foreground shadow-soft">
            <Sparkles className="h-3.5 w-3.5 text-coral" />
            For students & early-career engineers
          </span>
          <h1 className="mt-6 text-balance font-display text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
            Find the path to your <span className="text-coral">next role</span>.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-balance text-base text-muted-foreground sm:text-lg">
            Upload your resume, pick a target role, and get a week-by-week roadmap of skills, projects, and live jobs ranked by fit.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg" className="h-12 rounded-full bg-coral px-7 text-base text-coral-foreground hover:bg-coral/90 shadow-warm">
              <Link to="/onboarding">
                Start your atlas <ArrowRight className="ml-1 h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="h-12 rounded-full border-border bg-card px-7 text-base">
              <Link to="/onboarding">Sign in</Link>
            </Button>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">Sign in with Google • Free during beta</p>
        </div>

        <LiveJobs />
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="text-center">
          <h2 className="font-display text-3xl font-bold sm:text-4xl">How it works</h2>
          <p className="mt-3 text-muted-foreground">Three small steps. One clear path.</p>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {[
            {
              icon: FileText,
              n: "01",
              title: "Drop your resume",
              body: "We extract your skills, projects, and experience — no manual forms.",
            },
            {
              icon: Target,
              n: "02",
              title: "Pick a target role",
              body: "Tell us where you'd like to land. We compare your profile against the skills that role needs.",
            },
            {
              icon: Map,
              n: "03",
              title: "Follow your roadmap",
              body: "A vertical timeline of skills, courses, and projects — paced for your life.",
            },
          ].map((step) => {
            const Icon = step.icon;
            return (
              <div key={step.n} className="rounded-3xl border border-border bg-card p-7 shadow-soft transition-shadow hover:shadow-warm">
                <div className="flex items-center justify-between">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-primary-soft text-primary">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="font-display text-sm font-bold text-muted-foreground">{step.n}</span>
                </div>
                <h3 className="mt-5 font-display text-xl font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-6 md:grid-cols-2">
          <div className="rounded-3xl border border-border bg-card p-8 shadow-soft">
            <Briefcase className="h-6 w-6 text-coral" />
            <h3 className="mt-4 font-display text-2xl font-semibold">Real jobs, ranked by fit</h3>
            <p className="mt-2 text-muted-foreground">
              See match percentages, what you have, and what you're missing — for every role we surface.
            </p>
          </div>
          <div className="rounded-3xl border border-border bg-card p-8 shadow-soft">
            <Sparkles className="h-6 w-6 text-coral" />
            <h3 className="mt-4 font-display text-2xl font-semibold">Friendly, never overwhelming</h3>
            <p className="mt-2 text-muted-foreground">
              Bite-sized milestones, suggested side projects, and a checklist you can actually finish.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
        <div className="overflow-hidden rounded-3xl bg-primary p-10 text-primary-foreground shadow-warm sm:p-14">
          <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
            <div>
              <h2 className="font-display text-3xl font-bold sm:text-4xl">Your next role is closer than you think.</h2>
              <p className="mt-2 max-w-xl text-primary-foreground/80">
                Upload a resume and get your first gap analysis in a few minutes.
              </p>
            </div>
            <Button asChild size="lg" className="h-12 rounded-full bg-coral px-7 text-base text-coral-foreground hover:bg-coral/90">
              <Link to="/onboarding">
                Get started <ArrowRight className="ml-1 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <footer className="border-t border-border/60 bg-background/60 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 text-xs text-muted-foreground sm:flex-row sm:px-6">
          <p>© {new Date().getFullYear()} CareerAtlas</p>
        </div>
      </footer>
    </div>
  );
}

function LiveJobs() {
  const { data } = useQuery({
    queryKey: ["public-jobs"],
    queryFn: getPublicJobs,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const jobs = data?.jobs ?? [];
  // No placeholders: if there is nothing real to show, show nothing.
  if (jobs.length === 0) return null;
  const updated = data?.fetched_at
    ? new Date(data.fetched_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : null;

  return (
    <div className="mx-auto mt-14 max-w-5xl">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="font-display text-xl font-semibold">Hiring now</h2>
        {updated && <p className="text-xs text-muted-foreground">Live from Adzuna · updated {updated}</p>}
      </div>
      <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {jobs.slice(0, 9).map((job) => (
          <li key={job.apply_url}>
            <a
              href={job.apply_url}
              target="_blank"
              rel="noreferrer"
              className="group flex h-full flex-col rounded-2xl border border-border bg-card p-5 shadow-soft transition-shadow hover:shadow-warm"
            >
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                {job.role_title}
              </span>
              <span className="mt-2 line-clamp-2 font-display font-semibold leading-snug">{job.title}</span>
              <span className="mt-1 text-sm text-muted-foreground">{job.company || "Company not listed"}</span>
              <span className="mt-auto flex items-center justify-between gap-2 pt-4 text-xs text-muted-foreground">
                <span className="flex min-w-0 items-center gap-1">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{job.location || "Location not listed"}</span>
                </span>
                <ArrowUpRight className="h-4 w-4 shrink-0 text-primary transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
