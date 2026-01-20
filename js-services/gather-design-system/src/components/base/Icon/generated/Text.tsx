import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgText = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M10.4933 15.5H13.9933M12.2433 8.5V15.5M15.7433 10.084V8.889C15.7433 8.674 15.5693 8.5 15.3543 8.5H9.13235C8.91735 8.5 8.74335 8.674 8.74335 8.889V10.085M18.2433 21H6.24335C4.58635 21 3.24335 19.657 3.24335 18V6C3.24335 4.343 4.58635 3 6.24335 3H18.2433C19.9003 3 21.2433 4.343 21.2433 6V18C21.2433 19.657 19.9003 21 18.2433 21Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgText);
export default Memo;