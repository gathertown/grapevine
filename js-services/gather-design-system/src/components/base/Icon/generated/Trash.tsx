import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgTrash = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.6805 6.86111V19.1944C18.6805 20.3297 17.7602 21.25 16.625 21.25H7.37499C6.23974 21.25 5.31944 20.3297 5.31944 19.1944V6.86111M20.2222 6.86111H3.77777M8.40277 6.86111V6.34722C8.40277 4.36053 10.0133 2.75 12 2.75C13.9867 2.75 15.5972 4.36053 15.5972 6.34722V6.86111M9.94444 16.1111V12M14.0555 16.1111V12" stroke="currentColor" strokeWidth={1.54167} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgTrash);
export default Memo;