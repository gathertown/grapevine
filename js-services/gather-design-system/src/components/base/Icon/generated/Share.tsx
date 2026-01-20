import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgShare = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15.0012 8.99878H17.0021C18.1071 8.99878 19.0029 9.89458 19.0029 10.9996V19.0029C19.0029 20.108 18.1071 21.0038 17.0021 21.0038H6.9979C5.89287 21.0038 4.99707 20.108 4.99707 19.0029V10.9996C4.99707 9.89458 5.89287 8.99878 6.9979 8.99878H8.99874M12 15.0013V2.99628M12 2.99628L15.0012 5.99753M12 2.99628L8.99874 5.99753" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgShare);
export default Memo;