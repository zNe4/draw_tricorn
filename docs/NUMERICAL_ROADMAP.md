# Numerical methods and roadmap

This note records the numerical designs behind the parameter-ray and internal
basin-coordinate overlays for the holomorphic and antiholomorphic unicritical
families. Both first versions are implemented; the final section lists the most
useful extensions.

## Parameter rays

For the antiholomorphic family

\[
f_c(z)=\overline z^{\,d}+c,
\]

let \(\phi_c\) be the Böttcher coordinate tangent to the identity at infinity.
The dynamically defined parameter coordinate

\[
\Phi(c)=\phi_c(c)
\]

is the external parameter coordinate. A parameter ray is numerically traced as

\[
\mathcal R_\theta
  =\{\Phi^{-1}(r e^{2\pi i\theta}):r>1\}.
\]

Kawahira's continuation/Newton algorithm for Mandelbrot parameter rays can be
adapted, but not with one-complex-variable Newton iteration. The iterated
critical value depends on both \(c\) and \(\overline c\), so each Newton
correction must solve a real \(2\times2\) system.

For one radial sample \(w=r e^{2\pi i\theta}\), choose a depth \(n\) and use

\[
t=g^n(w),\qquad g(w)=\overline w^{\,d}.
\]

Thus

\[
t=r^{d^n}e^{2\pi i(-d)^n\theta}.
\]

Approximately solve \(f_c^n(c)=t\). Starting with \(z_0=c\), maintain the
Wirtinger derivatives

\[
a_k=\frac{\partial z_k}{\partial c},
\qquad
b_k=\frac{\partial z_k}{\partial\overline c}.
\]

The recurrence is

\[
\begin{aligned}
z_{k+1}&=\overline{z_k}^{\,d}+c,\\
a_{k+1}&=d\overline{z_k}^{\,d-1}\,\overline{b_k}+1,\\
b_{k+1}&=d\overline{z_k}^{\,d-1}\,\overline{a_k},
\end{aligned}
\]

with \(z_0=c,\ a_0=1,\ b_0=0\). If \(F=z_n-t\), solve

\[
a_n\,\delta c+b_n\,\overline{\delta c}=F
\]

by

\[
\delta c=
\frac{\overline{a_n}F-b_n\overline F}
{|a_n|^2-|b_n|^2},
\qquad
c_{\mathrm{new}}=c-\delta c.
\]

The implementation:

1. samples decreasing radial parameters as in Kawahira's depth/sharpness scheme;
2. uses the preceding ray point as the next Newton seed;
3. damps corrections that increase the residual;
4. rejects a step when the real Jacobian determinant is too small;
5. exposes depth, sharpness, and outer-radius controls;
6. keeps the last reliable point when continuation fails;
7. uses arbitrary precision when the parameter plane is already in that mode.

For \(f_c(z)=z^d+c\), the same continuation structure is used with ordinary
complex derivatives and the external angle map \(t\mapsto dt\). For
\(f_c(z)=\overline z^{\,d}+c\), the angle map is \(t\mapsto-dt\).

Unlike many familiar Mandelbrot rays, multicorn parameter rays need not
converge to one boundary point. Near odd-period parabolic components a ray can
accumulate on an arc. The current UI therefore calls its endpoint a final
numerical sample, not a landing point. Estimating the full accumulation set
remains future work.

## Internal Böttcher/Koenigs grand-orbit curves

The curves in Milnor's examples live in attracting Fatou components rather than
the basin of infinity. Begin with the attracting cycle already detected by the
application and let its period be \(p\).

For an antiholomorphic map, use a holomorphic return map

\[
F=
\begin{cases}
f_c^p,&p\text{ even},\\
f_c^{2p},&p\text{ odd}.
\end{cases}
\]

For an ordinary attracting point, compute a local Koenigs coordinate satisfying

\[
\psi(F(z))=\lambda\psi(z),\qquad 0<|\lambda|<1.
\]

For a superattracting return, compute a local Böttcher coordinate satisfying

\[
\psi(F(z))=\psi(z)^q
\]

for the appropriate local degree \(q\). Only \(|\psi|\) is required for the
curves, which avoids global argument-branch choices.

The implemented contour renderer:

1. classifies rendered pixels by their attracting basin and cycle phase;
2. iterates each basin point into a calibrated local coordinate neighborhood;
3. evaluates a scalar field \(\log|\psi|\);
4. extracts selected level curves with marching squares;
5. generates forward levels by multiplying the Koenigs radius by \(|\lambda|\),
   or raising the Böttcher radius to \(q\);
6. stops at unresolved basin points, escaped points, or the viewport limit.

The representative curve is drawn more boldly than its neighboring grand-orbit
levels. A later version can expose basin phases explicitly and permit selecting
an attracting component independently.

## Next extensions

1. Add parameter equipotentials using the parameter-coordinate solver.
2. Estimate and visualize parameter-ray accumulation sets near parabolic arcs.
3. Join continuation depth automatically to parameter-plane pixel scale.
4. Track internal basin phases and individual inverse branches.
5. Add perturbation rebasing for exceptionally deep arbitrary-precision zooms.

## References

- W. D. Crowe, R. Hasson, P. J. Rippon, and P. E. D. Strain-Clark, *On the
  structure of the Mandelbar set*, Nonlinearity 2 (1989), 541–553,
  [doi:10.1088/0951-7715/2/4/003](https://doi.org/10.1088/0951-7715/2/4/003).
- Sabyasachi Mukherjee, *Orbit portraits of unicritical antiholomorphic
  polynomials*, Conformal Geometry and Dynamics 19 (2015), 35–50,
  [doi:10.1090/S1088-4173-2015-00276-3](https://doi.org/10.1090/S1088-4173-2015-00276-3).
- Tomoki Kawahira, *An algorithm to draw external rays of the Mandelbrot set*
  (2009), [author's PDF](https://www1.econ.hit-u.ac.jp/kawahira/programs/mandel-exray.pdf).
- Hiroyuki Inou and Sabyasachi Mukherjee, *Non-landing parameter rays of the
  multicorns*, [arXiv:1406.3428](https://arxiv.org/abs/1406.3428).
- Sabyasachi Mukherjee, Shizuo Nakane, and Dierk Schleicher, *On multicorns and
  unicorns II: bifurcations in spaces of antiholomorphic polynomials*,
  [arXiv:1404.5031](https://arxiv.org/abs/1404.5031).
- John Milnor, *Dynamics in One Complex Variable*, sections on Böttcher and
  Koenigs linearization.
