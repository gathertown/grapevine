import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowRepeat = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M19.992 12.032C19.984 14.069 19.211 16.103 17.657 17.657C14.533 20.781 9.46703 20.781 6.34303 17.657C5.78703 17.101 5.33503 16.482 4.97703 15.826M4.00403 11.87C4.03603 9.866 4.81403 7.872 6.34303 6.343C9.46703 3.219 14.533 3.219 17.657 6.343C18.213 6.899 18.665 7.518 19.023 8.174M15.953 8.175H19.488V4.639M8.04703 15.825H4.51203V19.361" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowRepeat);
export default Memo;