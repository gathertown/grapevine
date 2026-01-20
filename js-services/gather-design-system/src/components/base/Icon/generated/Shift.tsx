import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgShift = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M2.91035 11.5511L11.2848 2.98185C11.6771 2.58043 12.3229 2.58043 12.7152 2.98185L21.0897 11.5511C21.7085 12.1843 21.2599 13.25 20.3745 13.25H17.1316V18.25C17.1316 19.3546 16.2361 20.25 15.1316 20.25H8.86845C7.76388 20.25 6.86845 19.3546 6.86845 18.25V13.25H3.62554C2.74016 13.25 2.29153 12.1843 2.91035 11.5511Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="square" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgShift);
export default Memo;