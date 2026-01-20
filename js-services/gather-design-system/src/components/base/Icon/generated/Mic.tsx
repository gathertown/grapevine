import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMic = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M19.9199 11.476C19.9199 15.85 16.374 19.3959 11.9999 19.3959M11.9999 19.3959C7.62585 19.3959 4.07996 15.85 4.07996 11.476M11.9999 19.3959L11.9999 21.5M12.0009 15.6999C9.96048 15.6999 8.30488 14.0459 8.30488 12.0055V6.19444C8.30488 4.15406 9.96048 2.5 12.0009 2.5C14.0412 2.5 15.6968 4.15406 15.6968 6.19444V12.0055C15.6968 14.0459 14.0412 15.6999 12.0009 15.6999Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMic);
export default Memo;