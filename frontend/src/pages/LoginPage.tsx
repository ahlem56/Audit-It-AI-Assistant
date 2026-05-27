import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react';
import { Navigate, useLocation, useSearchParams } from 'react-router-dom';
import { useAuthContext } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import pwcLogo from '../assets/pwc-logo.png';

export default function LoginPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { authenticated, authEnabled, config, login, loading } = useAuthContext();
  const { text } = useLanguage();

  const nextPath = searchParams.get('next') || '/';
  const error = searchParams.get('error_description') || searchParams.get('error');

  if (!loading && authenticated) {
    return <Navigate to={nextPath === '/login' ? '/' : nextPath} replace state={{ from: location }} />;
  }

  const trustPoints = [
    text.login.approvedUsersOnly,
    text.login.microsoftEntra,
    text.login.protectedWorkspace
  ];

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#f5f2ec] text-slate-950">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.95),_rgba(245,242,236,0.85)_42%,_rgba(225,226,230,0.75)_100%)]" />
      <div className="absolute inset-y-0 right-0 hidden w-[58%] bg-[radial-gradient(circle_at_18%_22%,rgba(255,255,255,0.42),transparent_30%),radial-gradient(circle_at_72%_30%,rgba(239,91,12,0.12),transparent_26%),linear-gradient(160deg,#d8dce2_0%,#b6bcc7_20%,#707887_52%,#2e3747_78%,#1a2230_100%)] lg:block" />
      <div className="absolute inset-y-0 right-0 hidden w-[58%] bg-[linear-gradient(to_right,rgba(255,255,255,0.0),rgba(255,255,255,0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.0),rgba(255,255,255,0.07)_1px,transparent_1px)] bg-[size:96px_96px] opacity-30 lg:block" />
      <div className="absolute right-[1%] top-[18%] hidden h-24 w-[40rem] -skew-x-[30deg] rounded-sm bg-[linear-gradient(90deg,rgba(239,91,12,0.85),#ff6a00)] shadow-[0_18px_60px_rgba(239,91,12,0.28)] lg:block" />
      <div className="absolute right-[16%] top-[58%] hidden h-16 w-[34rem] -skew-x-[30deg] rounded-sm bg-[linear-gradient(90deg,rgba(239,91,12,0.68),rgba(255,122,28,0.98))] lg:block" />
      <div className="absolute right-[10%] top-[14%] hidden h-72 w-72 rounded-full bg-[rgba(255,255,255,0.18)] blur-3xl lg:block" />
      <div className="absolute bottom-[8%] right-[6%] hidden h-64 w-64 rounded-full bg-[rgba(15,23,42,0.28)] blur-3xl lg:block" />

      <div className="relative mx-auto flex min-h-screen max-w-7xl items-center px-1 py-8 sm:px-6 lg:px-8">
        <div className="grid w-full items-center gap-12 lg:grid-cols-[minmax(0,1fr)_430px] lg:gap-16">
          <section className="relative max-w-[32rem] pb-2 lg:-ml-6 lg:justify-self-start xl:-ml-10">
            <div className="pwc-logo-shell inline-flex items-center gap-3 rounded-full border border-white/70 px-4 py-2 backdrop-blur">
              <img src={pwcLogo} alt="PwC logo" className="h-10 w-auto object-contain" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">Audit IT Assistant</span>
            </div>

            <div className="mt-10 space-y-5">
              <span className="inline-flex items-center gap-2 rounded-full border border-[#ef7c00]/20 bg-[#ef7c00]/10 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.28em] text-[#9a4d00]">
                <ShieldCheck className="h-4 w-4" />
                {text.login.internalAccess}
              </span>

              <h1 className="max-w-[9.5ch] font-['Georgia'] text-4xl leading-[0.98] tracking-[-0.03em] text-slate-950 sm:text-5xl lg:text-[4.6rem]">
                {text.login.titleLine1}
                <br />
                {text.login.titleLine2}
                <br />
                {text.login.titleLine3}
              </h1>

              <p className="max-w-sm text-base leading-7 text-slate-600">
                {text.login.subtitle}
              </p>
            </div>

            <div className="mt-10 flex max-w-sm flex-wrap gap-3">
              {trustPoints.map((point) => (
                <div
                  key={point}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-4 py-2 text-sm text-slate-700 shadow-[0_10px_24px_rgba(15,23,42,0.05)] backdrop-blur"
                >
                  <CheckCircle2 className="h-4 w-4 text-[#ef7c00]" />
                  <span>{point}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="relative flex justify-center lg:justify-end">
            <div className="absolute -inset-6 rounded-[36px] bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.7),rgba(255,255,255,0.0))] blur-2xl" />

            <div className="relative w-full max-w-[430px] overflow-hidden rounded-[32px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,245,238,0.94),rgba(255,255,255,0.80))] p-7 shadow-[0_32px_90px_rgba(15,23,42,0.22)] backdrop-blur-xl sm:p-8">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,#ef5b0c,#ff8c3a,#ef5b0c)]" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(239,91,12,0.18),_transparent_34%)]" />

              <div className="relative flex items-start justify-between gap-4">
                <div className="space-y-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">{text.login.authentication}</p>
                  <h2 className="font-['Georgia'] text-3xl leading-tight text-slate-950 sm:text-[2.2rem]">{text.login.welcomeBack}</h2>
                  <p className="text-sm leading-6 text-slate-600">{text.login.signInToContinue}</p>
                </div>
                <img src={pwcLogo} alt="PwC logo" className="h-11 w-auto object-contain sm:hidden" />
              </div>

              {error && (
                <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700">
                  {error}
                </div>
              )}

              {!authEnabled && config && (
                <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
                  {text.login.authDisabled}
                </div>
              )}

              <div className="relative mt-8 flex items-center justify-center p-2">
                <img src={pwcLogo} alt="PwC logo" className="h-16 w-auto object-contain opacity-95" />
              </div>

              <div className="relative mt-8 space-y-4">
                <button
                  type="button"
                  onClick={() => login(nextPath)}
                  className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-slate-950 px-5 py-4 text-sm font-semibold text-white shadow-[0_18px_36px_rgba(15,23,42,0.22)] transition duration-200 hover:bg-slate-800"
                >
                  {text.login.signInWithMicrosoft}
                  <ArrowRight className="h-4 w-4 transition duration-200 group-hover:translate-x-1" />
                </button>
                <p className="text-center text-xs leading-6 text-slate-500">{text.login.useApprovedAccount}</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
