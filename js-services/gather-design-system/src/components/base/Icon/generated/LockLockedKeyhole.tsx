import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgLockLockedKeyhole = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8 10V7C8 4.791 9.791 3 12 3C14.209 3 16 4.791 16 7V10M12 14V17M17 21H7C5.895 21 5 20.105 5 19V12C5 10.895 5.895 10 7 10H17C18.105 10 19 10.895 19 12V19C19 20.105 18.105 21 17 21Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgLockLockedKeyhole);
export default Memo;