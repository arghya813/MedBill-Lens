import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { PageSkeleton } from "@/components/Feedback";
import { AppMetaProvider } from "@/state/AppMeta";
import { BillSessionProvider } from "@/state/BillSession";
import { PreferencesProvider } from "@/state/Preferences";
import HomePage from "@/pages/HomePage";

// Route-level code splitting keeps the first paint small; the analysis and
// benchmark views pull in Recharts and are the heaviest.
const ReviewPage = lazy(() => import("@/pages/ReviewPage"));
const UploadPage = lazy(() => import("@/pages/UploadPage"));
const AnalysisPage = lazy(() => import("@/pages/AnalysisPage"));
const ReportPage = lazy(() => import("@/pages/ReportPage"));
const BenchmarksPage = lazy(() => import("@/pages/BenchmarksPage"));
const DemoPage = lazy(() => import("@/pages/DemoPage"));
const AboutPage = lazy(() => import("@/pages/AboutPage"));
const ProfilePage = lazy(() => import("@/pages/ProfilePage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

export default function App() {
  return (
    <AppMetaProvider>
      <PreferencesProvider>
        <BillSessionProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route
                path="upload"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading uploader" />}>
                    <UploadPage />
                  </Suspense>
                }
              />
              <Route
                path="review"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading review" />}>
                    <ReviewPage />
                  </Suspense>
                }
              />
              <Route
                path="bills/:billId"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading bill" />}>
                    <ReviewPage />
                  </Suspense>
                }
              />
              <Route
                path="bills/:billId/analysis"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading analysis" />}>
                    <AnalysisPage />
                  </Suspense>
                }
              />
              <Route
                path="bills/:billId/report"
                element={
                  <Suspense fallback={<PageSkeleton label="Building report" />}>
                    <ReportPage />
                  </Suspense>
                }
              />
              <Route
                path="benchmarks"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading benchmarks" />}>
                    <BenchmarksPage />
                  </Suspense>
                }
              />
              <Route
                path="demo"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading demo" />}>
                    <DemoPage />
                  </Suspense>
                }
              />
              <Route
                path="about"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading" />}>
                    <AboutPage />
                  </Suspense>
                }
              />
              <Route
                path="profile"
                element={
                  <Suspense fallback={<PageSkeleton label="Loading settings" />}>
                    <ProfilePage />
                  </Suspense>
                }
              />
              <Route
                path="*"
                element={
                  <Suspense fallback={<PageSkeleton />}>
                    <NotFoundPage />
                  </Suspense>
                }
              />
            </Route>
          </Routes>
        </BillSessionProvider>
      </PreferencesProvider>
    </AppMetaProvider>
  );
}