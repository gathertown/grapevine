import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgThumbUpFilled = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.1181 2.04792C12.6817 1.94211 12.2504 2.20028 12.0773 2.61462C11 6.50002 8 8.55501 8 11.2699V17.7252C8 18.8717 8.66361 20.0005 9.83559 20.4273C12.4864 21.3926 14.2335 21.589 16.9595 21.3527C19.0504 21.1715 20.6221 19.5685 21.0577 17.6326L21.9024 13.8781C22.4651 11.3773 20.5633 9.00007 18 9.00007L15 9.00002C15.4693 6.18434 16.615 2.89587 13.1181 2.04792Z" fill="currentColor" /><path d="M2 11C2 10.1716 2.67157 9.5 3.5 9.5H5.5C6.32843 9.5 7 10.1716 7 11V19C7 19.8284 6.32843 20.5 5.5 20.5H3.5C2.67157 20.5 2 19.8284 2 19V11Z" fill="currentColor" /></svg>;
const Memo = memo(SvgThumbUpFilled);
export default Memo;