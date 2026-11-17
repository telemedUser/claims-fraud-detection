import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import CustomerShell from './components/CustomerShell'
import { Spinner } from './components/ui'
import JourneyPage from './pages/journey/JourneyPage'
import ProcessingPage from './pages/ProcessingPage'
import ReportPage from './pages/ReportPage'

// Loaded on demand so internal console code is not part of the customer bundle.
const InternalPage = lazy(() => import('./pages/internal/InternalPage'))

export default function App() {
  return (
    <Routes>
      {/* Customer journey */}
      <Route element={<CustomerShell />}>
        <Route index element={<JourneyPage />} />
        <Route path="claims/:claimId/processing" element={<ProcessingPage />} />
        <Route path="claims/:claimId" element={<ReportPage />} />
      </Route>
      {/* Internal console: not linked from the journey; data requires the internal key */}
      <Route
        path="internal"
        element={
          <Suspense fallback={<div className="grid min-h-dvh place-items-center bg-slate-950"><Spinner className="size-8 text-white" /></div>}>
            <InternalPage />
          </Suspense>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
