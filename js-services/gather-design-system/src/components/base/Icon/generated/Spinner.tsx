import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSpinner = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M21.0037 12H18.0025M2.99622 12H5.99747M12 2.99622V5.99747M12 21.0037V18.0025M18.3666 18.3666L16.2447 16.2447M5.63331 5.63331L7.7552 7.7552M16.2447 7.7552L18.3666 5.63331M7.7552 16.2447L5.63331 18.3666" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSpinner);
export default Memo;