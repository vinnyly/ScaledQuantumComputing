module schrodinger_mod
    use, intrinsic :: iso_c_binding, only: c_double, c_int, c_double_complex

contains

    ! Compute the initial complex-valued Gaussian wave state
    subroutine compute_wave_matrix(size_n, matrix, num_steps, h_bar, mass)
        implicit none
        
        ! Scalar Inputs from Python (intent(in))
        integer, intent(in) :: size_n, num_steps
        real(c_double), intent(in) :: h_bar, mass
        
        ! 2D Array Output (intent(inout))
        complex(c_double_complex), intent(inout) :: matrix(size_n, size_n)
        
        ! Local variables
        integer :: i, j
        real(c_double) :: dx, dy, wave_value
        real(c_double) :: x, y

        dx = 1.0_c_double / real(size_n - 1, c_double)
        dy = 1.0_c_double / real(size_n - 1, c_double)
        
        do i = 1, size_n
            do j = 1, size_n
                x = (i - 1) * dx
                y = (j - 1) * dy
                
                ! Compute a simple Gaussian-like wave function approximation
                wave_value = exp(-100.0_c_double * ((x - 0.5_c_double)**2 + (y - 0.5_c_double)**2))
                
                ! Store result as complex (real part = Gaussian, imaginary part = 0)
                matrix(i, j) = cmplx(wave_value, 0.0_c_double, c_double_complex)
            end do
        end do
        
    end subroutine compute_wave_matrix

    ! Evolve the Schrödinger equation one time step on a ghost-cell-padded chunk
    ! padded: (nrows_padded x ncols) complex matrix with ghost rows at top and bottom
    ! is_top/is_bottom: 1 if this worker is at the grid boundary (wall condition)
    subroutine evolve_step(nrows_padded, ncols, padded, dt, is_top, is_bottom)
        implicit none
        
        integer, intent(in) :: nrows_padded, ncols, is_top, is_bottom
        real(c_double), intent(in) :: dt
        complex(c_double_complex), intent(inout) :: padded(nrows_padded, ncols)
        
        ! Local variables
        complex(c_double_complex) :: laplacian(nrows_padded, ncols)
        complex(c_double_complex) :: zero_c
        integer :: i, j

        zero_c = cmplx(0.0_c_double, 0.0_c_double, c_double_complex)
        laplacian = zero_c

        ! Compute the 5-point stencil Laplacian for interior rows (skip ghost rows)
        do i = 2, nrows_padded - 1
            do j = 1, ncols
                ! Up + Down - 4*Center
                laplacian(i, j) = padded(i-1, j) + padded(i+1, j) &
                                  - 4.0_c_double * padded(i, j)

                ! Left + Right (wrap edges like np.roll)
                if (j == 1) then
                    laplacian(i, j) = laplacian(i, j) + padded(i, ncols) + padded(i, 2)
                else if (j == ncols) then
                    laplacian(i, j) = laplacian(i, j) + padded(i, ncols-1) + padded(i, 1)
                else
                    laplacian(i, j) = laplacian(i, j) + padded(i, j-1) + padded(i, j+1)
                end if

                ! Wall boundary conditions (zero out edges)
                if (j == 1 .or. j == ncols) laplacian(i, j) = zero_c
                if (is_top == 1 .and. i == 2) laplacian(i, j) = zero_c
                if (is_bottom == 1 .and. i == nrows_padded - 1) laplacian(i, j) = zero_c
            end do
        end do

        ! Evolve: psi += 1j * laplacian * dt
        do i = 2, nrows_padded - 1
            do j = 1, ncols
                padded(i, j) = padded(i, j) + &
                    cmplx(0.0_c_double, 1.0_c_double, c_double_complex) * laplacian(i, j) * dt
            end do
        end do

    end subroutine evolve_step

end module schrodinger_mod