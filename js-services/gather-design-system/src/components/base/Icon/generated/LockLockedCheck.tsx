import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgLockLockedCheck = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 21H6C4.89543 21 4 20.1046 4 19V12C4 10.8954 4.89543 10 6 10H16C17.1046 10 18 10.8954 18 12V13M19 17L16.5 19.5L15 18M7 10V7C7 4.79086 8.79086 3 11 3C13.2091 3 15 4.79086 15 7V10" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgLockLockedCheck);
export default Memo;