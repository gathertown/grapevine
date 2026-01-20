import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgBlockQuote = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 25 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.49875 6.43668H17.61M20.5033 12H9.49875M9.49875 17.5633H17.61M5.00024 4.51733L5.00024 19.4827" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgBlockQuote);
export default Memo;